"""Moteur de synchronisation : connecteurs -> interactions REVORA.

Étapes d'une synchronisation :
  1. le connecteur récupère les événements (appels, emails) ;
  2. chaque événement est normalisé (format NormalizedEvent commun) ;
  3. il est rattaché à UN contact REVORA, dans cet ordre (cahier des charges) :
       a. identifiant CRM (HubSpot),
       b. téléphone normalisé — seulement s'il désigne un contact unique
          (plusieurs contacts peuvent partager un standard),
       c. email ;
     si aucun contact (ou plusieurs) ne correspond, l'événement est compté
     comme « non rattaché » et n'est pas enregistré ;
  4. les doublons sont écartés :
       a. même fournisseur + même identifiant externe (contrainte UNIQUE) ;
       b. même email vu par deux fournisseurs (Gmail ET HubSpot) : même
          Message-ID si les deux l'ont, sinon même contact, même sens,
          même objet (sans « Re: », « Fwd: »…) et moins de 3 minutes d'écart ;
  5. le résultat est journalisé (table integration_syncs).

Les saisies MANUELLES ne sont pas comparées aux événements synchronisés :
REVORA ne peut pas savoir si une note manuelle décrit le même échange.
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import database
from core import prospect_service
from core.deduplication import normalize_email, normalize_phone
from integrations.http import IntegrationError

DUPLICATE_WINDOW = timedelta(minutes=3)

SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|tr|aw)\s*:\s*)+", re.IGNORECASE)


# ==========================================
# RATTACHEMENT AUX CONTACTS
# ==========================================

def build_contact_index(prospects):
    """Index des contacts par identifiant HubSpot, téléphone normalisé et email."""

    index = {"hubspot": defaultdict(set), "phone": defaultdict(set), "email": defaultdict(set)}

    for prospect in prospects:
        if prospect.get("hubspot_id"):
            index["hubspot"][str(prospect["hubspot_id"])].add(prospect["id"])

        phone = normalize_phone(prospect.get("phone"))
        if phone:
            index["phone"][phone].add(prospect["id"])

        email = normalize_email(prospect.get("email"))
        if email:
            index["email"][email].add(prospect["id"])

    return index


def match_contact(event, index):
    """Retourne (contact_id, méthode) ou (None, raison).

    Une clé ambiguë (ex. standard partagé par plusieurs contacts) ne bloque
    pas : on passe à la clé suivante, qui peut désigner un contact unique.
    """

    keys = event.match_keys or {}
    ambiguity = None

    for method, values, normalize in (
        ("crm_id", keys.get("hubspot_contact_ids", []), str),
        ("phone", keys.get("phones", []), normalize_phone),
        ("email", keys.get("emails", []), normalize_email),
    ):
        bucket = {"crm_id": "hubspot", "phone": "phone", "email": "email"}[method]
        candidates = set()

        for value in values:
            key = normalize(value) if value else None
            if key:
                candidates |= index[bucket].get(key, set())

        if len(candidates) == 1:
            return candidates.pop(), method

        if len(candidates) > 1 and ambiguity is None:
            ambiguity = f"ambiguous {method} ({len(candidates)} contacts)"

    return None, ambiguity or "no matching contact"


# ==========================================
# DOUBLONS ENTRE FOURNISSEURS
# ==========================================

def normalize_subject(subject):
    """« RE: Fwd:  Proposition » -> « proposition »."""

    return re.sub(r"\s+", " ", SUBJECT_PREFIX.sub("", subject or "")).strip().casefold()


def is_cross_provider_duplicate(event, existing_interactions):
    """Vrai si cet email a déjà été enregistré par un AUTRE fournisseur."""

    if event.channel != "Email":
        return False

    message_id = (event.metadata or {}).get("message_id")
    subject = normalize_subject(event.subject)

    for item in existing_interactions:
        if item["channel"] != "Email" or item.get("provider") in (None, "manual", event.provider):
            continue

        other_id = (item.get("metadata") or {}).get("message_id")

        if message_id and other_id:
            if message_id == other_id:
                return True
            continue

        if item.get("direction") != event.direction or normalize_subject(item.get("subject")) != subject:
            continue

        stored = datetime.fromisoformat(item["occurred_at"]).replace(tzinfo=timezone.utc)

        if abs(stored - event.occurred_at) <= DUPLICATE_WINDOW:
            return True

    return False


# ==========================================
# SYNCHRONISATION
# ==========================================

def _state_key(provider):
    return f"sync_state:{provider}"


def run_sync(connector, full=False, now=None):
    """Synchronise un connecteur et retourne le bilan.

    full=True ignore la mémoire de la dernière synchronisation (tout relire).
    Relancer une synchronisation ne crée jamais de doublon.
    """

    provider = connector.provider
    now = now or datetime.now(timezone.utc)
    state = {} if full else database.get_setting(_state_key(provider), {})

    since = None
    if state.get("last_success"):
        since = datetime.fromisoformat(state["last_success"])

    if hasattr(connector, "state"):
        connector.state = dict(state.get("connector_state", {}))

    counts = {"fetched": 0, "created": 0, "duplicates": 0, "unmatched": 0, "errors": 0}
    problems = []

    try:
        connector.authenticate()
        raw_events = connector.fetch_events(since)

    except IntegrationError as error:
        counts["errors"] = 1
        database.log_sync(provider, "failed", counts, str(error))
        database.set_integration_status(provider, "Error", str(error))
        return {"status": "failed", "message": str(error), **counts}

    counts["fetched"] = len(raw_events)
    index = build_contact_index(database.get_all_prospects())
    existing = {}

    for raw in raw_events:
        try:
            event = connector.normalize_event(raw)
        except (IntegrationError, KeyError, ValueError) as error:
            counts["errors"] += 1
            problems.append(str(error))
            continue

        contact_id, how = match_contact(event, index)

        if contact_id is None:
            counts["unmatched"] += 1
            continue

        if contact_id not in existing:
            existing[contact_id] = database.get_interactions(contact_id)

        if is_cross_provider_duplicate(event, existing[contact_id]):
            counts["duplicates"] += 1
            continue

        occurred_utc = event.occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        metadata = {**(event.metadata or {}), "matched_by": how}

        inserted = database.add_external_interaction(
            contact_id, provider, event.external_id, event.channel, event.direction,
            event.event_type, occurred_utc, event.subject, event.content, metadata,
        )

        if inserted:
            counts["created"] += 1
            existing[contact_id].append({
                "channel": event.channel, "provider": provider, "direction": event.direction,
                "subject": event.subject, "occurred_at": occurred_utc, "metadata": metadata,
            })
        else:
            counts["duplicates"] += 1

    status = "success" if not problems else "partial"
    message = "; ".join(problems[:5]) if problems else None

    database.set_setting(_state_key(provider), {
        "last_success": now.isoformat(),
        "connector_state": getattr(connector, "state", {}),
    })
    database.log_sync(provider, status, counts, message)
    database.set_integration_status(provider, "Connected", message, synced=True)

    return {"status": status, "message": message, **counts}


# ==========================================
# IMPORT DES CONTACTS HUBSPOT
# ==========================================

def import_hubspot_contacts(connector):
    """Importe les contacts HubSpot comme prospects REVORA.

    - contact déjà relié (même hubspot_id) : ignoré ;
    - prospect existant avec le même email : relié à HubSpot (rien n'est écrasé) ;
    - sinon : création, avec les contrôles habituels (doublons, champs obligatoires).
      Un contact sans entreprise est REJETÉ plutôt que complété par supposition.
    """

    report = {"created": 0, "linked": 0, "already_linked": 0, "errors": []}

    connector.authenticate()
    records = connector.fetch_contacts()
    prospects = database.get_all_prospects()

    linked_ids = {str(p["hubspot_id"]) for p in prospects if p.get("hubspot_id")}
    by_email = {
        normalize_email(p["email"]): p for p in prospects
        if normalize_email(p.get("email")) and not p.get("hubspot_id")
    }

    for record in records:
        data = connector.normalize_contact(record)

        if data["hubspot_id"] in linked_ids:
            report["already_linked"] += 1
            continue

        existing = by_email.get(normalize_email(data.get("email")))

        if existing:
            database.set_hubspot_id(existing["id"], data["hubspot_id"])
            linked_ids.add(data["hubspot_id"])
            by_email.pop(normalize_email(data.get("email")))
            report["linked"] += 1
            continue

        ok, message = prospect_service.create_prospect({**data, "source": "HubSpot"})

        if ok:
            report["created"] += 1
            linked_ids.add(data["hubspot_id"])
        else:
            report["errors"].append({"hubspot_id": data["hubspot_id"], "reason": message})

    return report
