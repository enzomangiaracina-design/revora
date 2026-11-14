"""Connecteur HubSpot — version hors ligne, testée avec des données fictives.

Ce qui a été VÉRIFIÉ dans la documentation officielle (le 14/11/2026) :
  - objets "calls" et "emails", recherche POST .../{objet}/search avec
    filterGroups, sorts (une seule règle), limit ≤ 200, pagination "after",
    10 000 résultats maximum par requête, 5 requêtes/seconde pour la recherche ;
  - appels : hs_timestamp, hs_call_direction (INBOUND / OUTBOUND),
    hs_call_duration (millisecondes), hs_call_status, hs_call_disposition
    (identifiants GUID pour les résultats par défaut), hs_call_to_number,
    hs_call_from_number, hs_call_title, hs_call_body ;
  - emails : hs_timestamp, hs_email_direction (EMAIL / INCOMING_EMAIL /
    FORWARDED_EMAIL), hs_email_subject, hs_email_text, hs_email_status,
    hs_email_from_email, hs_email_to_email, hs_email_headers ;
  - lecture du contenu des emails : scope "sales-email-read".

Ce qui n'est PAS documenté et devra être confirmé sur un compte de TEST :
  - la forme exacte de la réponse de lecture des associations ;
  - un éventuel Message-ID dans hs_email_headers (lu s'il existe, jamais supposé) ;
  - la version d'API à utiliser : la documentation montre /crm/v3/objects
    et des chemins datés (/crm/objects/2026-09) ; le préfixe est donc réglable.

Authentification prévue : jeton d'accès (variable HUBSPOT_ACCESS_TOKEN) d'une
application privée créée par l'utilisateur sur un compte de test.
"""

import json
from datetime import datetime, timezone

from integrations.base import BaseConnector, NormalizedEvent
from integrations.config import get_secret
from integrations.http import HttpClient, IntegrationError

BASE_URL = "https://api.hubapi.com"
DEFAULT_OBJECTS_PREFIX = "/crm/v3/objects"
ASSOCIATIONS_PREFIX = "/crm/v3/associations"

PAGE_SIZE = 100
MAX_RESULTS = 10_000  # limite documentée de l'API de recherche

CONTACT_PROPERTIES = [
    "firstname", "lastname", "email", "phone", "mobilephone",
    "jobtitle", "company", "hs_lastmodifieddate",
]

CALL_PROPERTIES = [
    "hs_timestamp", "hs_call_direction", "hs_call_duration", "hs_call_status",
    "hs_call_disposition", "hs_call_to_number", "hs_call_from_number",
    "hs_call_title", "hs_call_body", "hs_lastmodifieddate",
]

EMAIL_PROPERTIES = [
    "hs_timestamp", "hs_email_direction", "hs_email_subject", "hs_email_text",
    "hs_email_status", "hs_email_from_email", "hs_email_to_email",
    "hs_email_headers", "hs_lastmodifieddate",
]

# Résultats d'appel par défaut documentés (GUID HubSpot -> résultat REVORA)
CALL_DISPOSITIONS = {
    "f240bbac-87c9-4f6e-bf70-924b57d47db7": "Completed",   # Connected
    "73a0d17f-1163-4015-bdd5-ec830791da20": "No answer",   # No answer
    "b2cf5968-551e-4856-9783-52b3da59a7d0": "Voicemail",   # Left voicemail
    "a4c4c377-d246-4b32-a13b-75a56a4cd0ff": "Voicemail",   # Left live message
    "9d9162e7-6cf3-4944-bf63-4dff82258764": "No answer",   # Busy
    "17b47fee-58de-441e-a44c-c6300d46f273": "Other",       # Wrong number
}

UNREACHED_STATUSES = {"NO_ANSWER", "BUSY", "FAILED", "CANCELED"}

CALL_DIRECTIONS = {"INBOUND": "Inbound", "OUTBOUND": "Outbound"}

EMAIL_DIRECTIONS = {
    "EMAIL": "Outbound",            # envoyé depuis le CRM ou enregistré en copie
    "INCOMING_EMAIL": "Inbound",    # réponse à un email enregistré
    "FORWARDED_EMAIL": "Internal",  # transféré au CRM : sens d'origine inconnu
}


class HubSpotConnector(BaseConnector):

    provider = "hubspot"

    def __init__(self, token=None, transport=None, objects_prefix=DEFAULT_OBJECTS_PREFIX,
                 include_content=False, sleep=None):
        """
        include_content : False par défaut (minimisation des données, RGPD) :
                          le texte des emails et des notes d'appel n'est pas importé.
        """

        self.token = token
        self.transport = transport
        self.objects_prefix = objects_prefix
        self.include_content = include_content
        self.sleep = sleep
        self.client = None

    # ---------- Interface commune ----------

    def authenticate(self):
        token = self.token or get_secret("HUBSPOT_ACCESS_TOKEN")

        if not token:
            raise IntegrationError(
                "HUBSPOT_ACCESS_TOKEN is not set. Create a private app on a HubSpot "
                "TEST account and put its token in the .env file."
            )

        kwargs = {"transport": self.transport}
        if self.sleep:
            kwargs["sleep"] = self.sleep

        self.client = HttpClient(BASE_URL, token, **kwargs)

    def test_connection(self):
        """Vrai si l'API répond avec ce jeton (lecture d'un seul contact)."""

        try:
            self._client().request("GET", f"{self.objects_prefix}/contacts", params={"limit": 1})
            return True
        except IntegrationError:
            return False

    def fetch_events(self, since=None):
        """Appels et emails modifiés depuis `since` (datetime UTC), avec leurs contacts associés."""

        events = []

        for kind, object_type, properties in (
            ("call", "calls", CALL_PROPERTIES),
            ("email", "emails", EMAIL_PROPERTIES),
        ):
            records = self._search(object_type, properties, since)
            contacts = self._associated_contacts(object_type, [r["id"] for r in records])

            for record in records:
                events.append({
                    "kind": kind,
                    "id": str(record["id"]),
                    "properties": record.get("properties", {}),
                    "contact_ids": contacts.get(str(record["id"]), []),
                })

        return events

    def normalize_event(self, raw_event):
        if raw_event["kind"] == "call":
            return self._normalize_call(raw_event)
        return self._normalize_email(raw_event)

    # ---------- Contacts ----------

    def fetch_contacts(self, since=None):
        """Contacts HubSpot (propriétés utiles à REVORA)."""

        return self._search("contacts", CONTACT_PROPERTIES, since)

    @staticmethod
    def normalize_contact(record):
        """Contact HubSpot -> dictionnaire au format d'un prospect REVORA."""

        p = record.get("properties", {})

        return {
            "hubspot_id": str(record["id"]),
            "first_name": (p.get("firstname") or "").strip(),
            "last_name": (p.get("lastname") or "").strip(),
            "company_name": (p.get("company") or "").strip(),
            "email": p.get("email"),
            "phone": p.get("phone") or p.get("mobilephone"),
            "job_title": p.get("jobtitle"),
        }

    # ---------- Outils internes ----------

    def _client(self):
        if self.client is None:
            self.authenticate()
        return self.client

    def _search(self, object_type, properties, since):
        """Recherche paginée, triée par date de modification croissante."""

        body = {
            "properties": properties,
            "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
            "limit": PAGE_SIZE,
        }

        if since:
            body["filterGroups"] = [{"filters": [{
                "propertyName": "hs_lastmodifieddate",
                "operator": "GTE",
                "value": str(to_epoch_ms(since)),
            }]}]

        results = []
        after = None

        while len(results) < MAX_RESULTS:
            if after:
                body["after"] = after

            page = self._client().request(
                "POST", f"{self.objects_prefix}/{object_type}/search", body=body
            )

            results.extend(page.get("results", []))
            after = ((page.get("paging") or {}).get("next") or {}).get("after")

            if not after:
                break

        return results

    def _associated_contacts(self, object_type, ids):
        """{id_objet: [ids de contacts]} via la lecture groupée des associations.

        La forme de la réponse n'étant pas documentée sur les pages lues, la
        lecture accepte "id" ou "toObjectId" (à confirmer sur un compte de test).
        """

        associations = {}

        for start in range(0, len(ids), PAGE_SIZE):
            chunk = ids[start:start + PAGE_SIZE]

            if not chunk:
                continue

            response = self._client().request(
                "POST",
                f"{ASSOCIATIONS_PREFIX}/{object_type}/contacts/batch/read",
                body={"inputs": [{"id": str(i)} for i in chunk]},
            )

            for result in response.get("results", []):
                source = str((result.get("from") or {}).get("id"))
                associations[source] = [
                    str(item.get("id") or item.get("toObjectId"))
                    for item in result.get("to", [])
                    if item.get("id") or item.get("toObjectId")
                ]

        return associations

    def _normalize_call(self, raw):
        p = raw["properties"]
        direction = CALL_DIRECTIONS.get((p.get("hs_call_direction") or "").upper())

        disposition = CALL_DISPOSITIONS.get(p.get("hs_call_disposition") or "")
        status = (p.get("hs_call_status") or "").upper()

        if disposition:
            event_type = disposition
        elif status in UNREACHED_STATUSES:
            event_type = "No answer"
        else:
            # Prudence : un appel "terminé" sans résultat n'est pas forcément
            # une conversation ; on ne l'invente pas.
            event_type = "Other"

        counterpart = p.get("hs_call_from_number") if direction == "Inbound" else p.get("hs_call_to_number")

        metadata = {"hubspot_call_status": status or None}
        duration = _to_int(p.get("hs_call_duration"))
        if duration:
            metadata["duration_seconds"] = duration // 1000

        return NormalizedEvent(
            provider=self.provider,
            external_id=f"call:{raw['id']}",
            channel="Call",
            direction=direction,
            event_type=event_type,
            occurred_at=parse_hubspot_time(p.get("hs_timestamp")),
            subject=p.get("hs_call_title"),
            content=p.get("hs_call_body") if self.include_content else None,
            match_keys={
                "hubspot_contact_ids": raw.get("contact_ids", []),
                "phones": [counterpart] if counterpart else [],
                "emails": [],
            },
            metadata=metadata,
        )

    def _normalize_email(self, raw):
        p = raw["properties"]
        direction = EMAIL_DIRECTIONS.get((p.get("hs_email_direction") or "").upper())
        status = (p.get("hs_email_status") or "").upper()

        if direction == "Inbound":
            counterpart = p.get("hs_email_from_email")
        else:
            counterpart = p.get("hs_email_to_email")

        emails = [e.strip() for e in (counterpart or "").replace(",", ";").split(";") if e.strip()]

        metadata = {"hubspot_email_status": status or None}
        message_id = _message_id_from_headers(p.get("hs_email_headers"))
        if message_id:
            metadata["message_id"] = message_id

        return NormalizedEvent(
            provider=self.provider,
            external_id=f"email:{raw['id']}",
            channel="Email",
            direction=direction,
            event_type="Other" if status in {"BOUNCED", "FAILED"} else "Completed",
            occurred_at=parse_hubspot_time(p.get("hs_timestamp")),
            subject=p.get("hs_email_subject"),
            content=p.get("hs_email_text") if self.include_content else None,
            match_keys={
                "hubspot_contact_ids": raw.get("contact_ids", []),
                "phones": [],
                "emails": emails,
            },
            metadata=metadata,
        )


# ---------- Fonctions utilitaires ----------

def to_epoch_ms(moment):
    """datetime -> millisecondes depuis 1970 (format des filtres de date HubSpot)."""

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return int(moment.timestamp() * 1000)


def parse_hubspot_time(value):
    """hs_timestamp : texte ISO 8601 ("2026-11-14T09:30:00Z") ou millisecondes -> datetime UTC."""

    if value in (None, ""):
        raise IntegrationError("Event without hs_timestamp")

    text = str(value)

    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)

    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))

    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _message_id_from_headers(headers):
    """Cherche un Message-ID dans hs_email_headers (non documenté : jamais supposé présent)."""

    if not headers:
        return None

    try:
        data = json.loads(headers) if isinstance(headers, str) else headers
    except ValueError:
        return None

    if not isinstance(data, dict):
        return None

    for key, value in data.items():
        if key.replace("-", "").replace("_", "").lower() == "messageid" and value:
            return str(value).strip()

    return None
