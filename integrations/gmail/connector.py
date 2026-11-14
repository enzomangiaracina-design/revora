"""Connecteur Gmail — version hors ligne, testée avec des données fictives.

Ce qui a été VÉRIFIÉ dans la documentation officielle (le 14/11/2026) :
  - toutes les autorisations de lecture Gmail (gmail.metadata, gmail.readonly,
    gmail.modify, mail.google.com) sont classées « RESTREINTES » : une
    application publique doit passer la vérification Google, et un audit de
    sécurité si les données sont stockées sur un serveur ;
  - gmail.metadata donne les en-têtes et libellés, PAS le contenu ; avec cette
    autorisation, le paramètre de recherche `q` est interdit ;
  - messages.list : maxResults (défaut 100, max 500), pageToken ; chaque
    message n'y contient que id et threadId ;
  - messages.get : format=metadata + metadataHeaders ;
  - synchronisation : complète la première fois, puis partielle avec
    history.list(startHistoryId) ; HTTP 404 = historique expiré -> refaire
    une synchronisation complète.

Choix REVORA : autorisation minimale gmail.metadata (aucun corps d'email).

Non confirmé sur les pages lues, à vérifier sur un compte de TEST :
  - l'unité d'internalDate (millisecondes attendues) : l'en-tête Date sert de secours ;
  - la forme exacte des enregistrements d'historique (messagesAdded).

Authentification prévue : jeton OAuth (variable GMAIL_ACCESS_TOKEN) obtenu
par l'utilisateur pour SA boîte de test ; adresse de la boîte : GMAIL_USER_EMAIL.
"""

from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from integrations.base import BaseConnector, NormalizedEvent
from integrations.config import get_secret
from integrations.http import HttpClient, IntegrationError

BASE_URL = "https://gmail.googleapis.com"
API = "/gmail/v1/users/me"

HEADERS = ["From", "To", "Cc", "Subject", "Date", "Message-ID"]

# Messages ignorés : brouillons, spam, corbeille
IGNORED_LABELS = {"DRAFT", "SPAM", "TRASH"}

DEFAULT_MAX_MESSAGES = 500


class GmailConnector(BaseConnector):

    provider = "gmail"

    def __init__(self, token=None, user_email=None, transport=None,
                 max_messages=DEFAULT_MAX_MESSAGES, state=None, sleep=None):
        """
        state : mémoire de la dernière synchronisation ({"history_id": ...}),
                conservée par REVORA entre deux synchronisations.
        """

        self.token = token
        self.user_email = user_email
        self.transport = transport
        self.max_messages = max_messages
        self.state = dict(state or {})
        self.sleep = sleep
        self.client = None
        self.last_sync_mode = None

    # ---------- Interface commune ----------

    def authenticate(self):
        token = self.token or get_secret("GMAIL_ACCESS_TOKEN")

        if not token:
            raise IntegrationError(
                "GMAIL_ACCESS_TOKEN is not set. Gmail read scopes are RESTRICTED by Google: "
                "use a TEST mailbox and an OAuth token you generated yourself."
            )

        self.user_email = (self.user_email or get_secret("GMAIL_USER_EMAIL") or "").lower() or None

        kwargs = {"transport": self.transport}
        if self.sleep:
            kwargs["sleep"] = self.sleep

        self.client = HttpClient(BASE_URL, token, **kwargs)

    def test_connection(self):
        try:
            self._client().request("GET", f"{API}/messages", params={"maxResults": 1})
            return True
        except IntegrationError:
            return False

    def fetch_events(self, since=None):
        """Messages nouveaux depuis la dernière synchronisation.

        Synchronisation partielle si un history_id est connu, sinon complète.
        `since` (datetime UTC) filtre en plus les messages trop anciens.
        Met à jour self.state["history_id"].
        """

        ids = None

        if self.state.get("history_id"):
            try:
                ids = self._ids_from_history(self.state["history_id"])
                self.last_sync_mode = "partial"
            except IntegrationError as error:
                if error.status != 404:
                    raise
                ids = None  # historique expiré : synchronisation complète

        if ids is None:
            ids = self._recent_ids()
            self.last_sync_mode = "full"

        messages = []

        for message_id in ids:
            message = self._client().request(
                "GET", f"{API}/messages/{message_id}",
                params={"format": "metadata", "metadataHeaders": HEADERS},
            )
            messages.append(message)

        history_ids = [int(m["historyId"]) for m in messages if str(m.get("historyId", "")).isdigit()]
        if history_ids:
            self.state["history_id"] = str(max(history_ids + [int(self.state.get("history_id") or 0)]))

        messages = [m for m in messages if not IGNORED_LABELS & set(m.get("labelIds", []))]

        if since:
            messages = [m for m in messages if message_time(m) >= _aware(since)]

        return messages

    def normalize_event(self, raw_event):
        headers = header_map(raw_event)

        sender = parseaddr(headers.get("from", ""))[1].lower()
        recipients = [
            address.lower()
            for _, address in getaddresses([headers.get("to", ""), headers.get("cc", "")])
            if address
        ]

        outbound = (
            (self.user_email and sender == self.user_email)
            or "SENT" in raw_event.get("labelIds", [])
        )

        if outbound:
            direction, counterparts = "Outbound", recipients
        else:
            direction, counterparts = "Inbound", [sender] if sender else []

        if self.user_email:
            counterparts = [c for c in counterparts if c != self.user_email]

        metadata = {"thread_id": raw_event.get("threadId")}
        if headers.get("message-id"):
            metadata["message_id"] = headers["message-id"].strip()

        return NormalizedEvent(
            provider=self.provider,
            external_id=str(raw_event["id"]),
            channel="Email",
            direction=direction,
            event_type="Completed",
            occurred_at=message_time(raw_event),
            subject=headers.get("subject"),
            content=None,  # gmail.metadata : pas d'accès au contenu
            match_keys={"hubspot_contact_ids": [], "phones": [], "emails": counterparts},
            metadata=metadata,
        )

    # ---------- Outils internes ----------

    def _client(self):
        if self.client is None:
            self.authenticate()
        return self.client

    def _recent_ids(self):
        """Synchronisation complète : identifiants des messages les plus récents."""

        ids, page_token = [], None

        while len(ids) < self.max_messages:
            params = {"maxResults": min(100, self.max_messages - len(ids))}
            if page_token:
                params["pageToken"] = page_token

            page = self._client().request("GET", f"{API}/messages", params=params)
            ids.extend(m["id"] for m in page.get("messages", []))
            page_token = page.get("nextPageToken")

            if not page_token:
                break

        return ids

    def _ids_from_history(self, start_history_id):
        """Synchronisation partielle : messages ajoutés depuis start_history_id."""

        ids, page_token = [], None

        while True:
            params = {"startHistoryId": start_history_id, "historyTypes": "messageAdded"}
            if page_token:
                params["pageToken"] = page_token

            page = self._client().request("GET", f"{API}/history", params=params)

            for record in page.get("history", []):
                for added in record.get("messagesAdded", []):
                    message_id = (added.get("message") or {}).get("id")
                    if message_id and message_id not in ids:
                        ids.append(message_id)

            page_token = page.get("nextPageToken")

            if not page_token or len(ids) >= self.max_messages:
                break

        return ids[:self.max_messages]


# ---------- Fonctions utilitaires ----------

def header_map(message):
    """En-têtes d'un message -> {nom en minuscules: valeur}."""

    return {
        h["name"].lower(): h.get("value", "")
        for h in (message.get("payload") or {}).get("headers", [])
        if h.get("name")
    }


def message_time(message):
    """Date du message en UTC : internalDate (ms) ou, à défaut, l'en-tête Date."""

    internal = str(message.get("internalDate") or "")

    if internal.isdigit():
        return datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)

    date_header = header_map(message).get("date")

    if date_header:
        return _aware(parsedate_to_datetime(date_header))

    raise IntegrationError(f"Message {message.get('id')} has no date")


def _aware(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
