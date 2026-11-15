"""Indicateurs de performance individuels du SDR.

Toutes les définitions sont explicites (affichées dans l'application) et
calculées uniquement à partir des interactions, objections et relances
réellement enregistrées. Les dates utilisées sont en heure LOCALE.

Définitions :
  - Appels effectués      : appels sortants de la période.
  - Appels par jour       : appels effectués / jours ouvrés (lundi-vendredi) de la période.
  - Taux de connexion     : appels sortants ayant abouti à une conversation
                            (résultat Completed, Positive response, Objection,
                            Meeting booked ou Information shared) / appels sortants.
  - Emails envoyés / reçus : emails sortants / entrants de la période.
  - Prospects contactés   : prospects ayant reçu au moins une prise de contact
                            sortante (appel, email, LinkedIn) pendant la période.
  - Taux de réponse       : prospects contactés qui ont réagi (email, appel ou
                            message LinkedIn ENTRANT) après leur premier contact
                            sortant de la période / prospects contactés.
  - Rendez-vous obtenus   : interactions dont le résultat est « Meeting booked ».
  - Taux de conversion    : prospects contactés ayant obtenu un rendez-vous
                            pendant la période / prospects contactés.
  - Délai moyen de relance : nombre moyen de jours entre deux prises de contact
                            sortantes successives auprès du même prospect
                            (la seconde ayant lieu pendant la période).
  - Invitations LinkedIn  : demandes de connexion envoyées pendant la période.
  - Taux d'acceptation    : prospects invités pendant la période qui ont accepté
                            ensuite (pendant la période) / prospects invités.
  Une invitation acceptée n'est PAS comptée comme une réponse.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from core.scoring import CONVERSATION_RESULTS

OUTBOUND_CHANNELS = {"Call", "Email", "LinkedIn"}
REACTION_CHANNELS = {"Call", "Email", "LinkedIn"}

PERIODS = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}


# ==========================================
# PÉRIODES
# ==========================================

def period_range(days, today=None):
    """(début, fin) d'une période de `days` jours se terminant aujourd'hui."""

    end = today or date.today()

    return end - timedelta(days=days - 1), end


def previous_range(start, end):
    """Période précédente de même durée (pour la comparaison)."""

    length = (end - start).days + 1

    return start - timedelta(days=length), start - timedelta(days=1)


def working_days(start, end):
    """Nombre de jours ouvrés (lundi-vendredi) entre deux dates incluses."""

    return sum(
        1 for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
    )


def _day(item):
    return date.fromisoformat(item["occurred_at_local"][:10])


def in_range(items, start, end):
    """Éléments dont la date locale est comprise entre start et end inclus."""

    return [item for item in items if item.get("occurred_at_local") and start <= _day(item) <= end]


def _ratio(numerator, denominator):
    """Pourcentage arrondi, ou None si le dénominateur est nul (pas de 0 % trompeur)."""

    return round(numerator / denominator * 100) if denominator else None


# ==========================================
# INDICATEURS
# ==========================================

def outbound_touches(interactions):
    return [
        i for i in interactions
        if i["direction"] == "Outbound" and i["channel"] in OUTBOUND_CHANNELS
    ]


def follow_up_delay(all_interactions, start, end):
    """Délai moyen (jours, 1 décimale) entre deux contacts sortants successifs du même prospect.

    Seuls les intervalles dont le second contact est dans la période comptent.
    Retourne None s'il n'y a aucune relance.
    """

    by_contact = defaultdict(list)

    for item in outbound_touches(all_interactions):
        by_contact[item["contact_id"]].append(datetime.fromisoformat(item["occurred_at_local"]))

    gaps = []

    for moments in by_contact.values():
        moments.sort()

        for previous, current in zip(moments, moments[1:]):
            if start <= current.date() <= end:
                gaps.append((current - previous).total_seconds() / 86400)

    return round(sum(gaps) / len(gaps), 1) if gaps else None


def compute_kpis(all_interactions, objections, start, end):
    """Indicateurs de la période [start, end] (dates locales incluses)."""

    period = in_range(all_interactions, start, end)
    outbound = outbound_touches(period)

    calls = [i for i in outbound if i["channel"] == "Call"]
    connected = [i for i in calls if i["event_type"] in CONVERSATION_RESULTS]
    emails_sent = [i for i in outbound if i["channel"] == "Email"]
    emails_received = [i for i in period if i["channel"] == "Email" and i["direction"] == "Inbound"]

    first_touch = {}
    for item in sorted(outbound, key=lambda i: i["occurred_at_local"]):
        first_touch.setdefault(item["contact_id"], item["occurred_at_local"])

    replied = {
        i["contact_id"] for i in period
        if i["direction"] == "Inbound" and i["channel"] in REACTION_CHANNELS
        and i["event_type"] != "Connection accepted"
        and i["contact_id"] in first_touch and i["occurred_at_local"] > first_touch[i["contact_id"]]
    }

    meetings = [i for i in period if i["event_type"] == "Meeting booked"]
    converted = {i["contact_id"] for i in meetings} & set(first_touch)

    days = working_days(start, end)
    period_objections = in_range(objections, start, end)

    first_request = {}
    for item in sorted(period, key=lambda i: i["occurred_at_local"]):
        if item["channel"] == "LinkedIn" and item["event_type"] == "Connection request sent":
            first_request.setdefault(item["contact_id"], item["occurred_at_local"])

    accepted = {
        i["contact_id"] for i in period
        if i["channel"] == "LinkedIn" and i["event_type"] == "Connection accepted"
        and i["contact_id"] in first_request and i["occurred_at_local"] > first_request[i["contact_id"]]
    }

    return {
        "calls": len(calls),
        "calls_per_day": round(len(calls) / days, 1) if days else None,
        "connection_rate": _ratio(len(connected), len(calls)),
        "emails_sent": len(emails_sent),
        "emails_per_day": round(len(emails_sent) / days, 1) if days else None,
        "emails_received": len(emails_received),
        "contacted": len(first_touch),
        "replied": len(replied),
        "reply_rate": _ratio(len(replied), len(first_touch)),
        "meetings": len(meetings),
        "conversion_rate": _ratio(len(converted), len(first_touch)),
        "objections": len(period_objections),
        "follow_up_delay": follow_up_delay(all_interactions, start, end),
        "linkedin_requests": sum(
            1 for i in period
            if i["channel"] == "LinkedIn" and i["event_type"] == "Connection request sent"
        ),
        "linkedin_acceptance_rate": _ratio(len(accepted), len(first_request)),
        "invited": len(first_request),
        "linkedin_messages": sum(
            1 for i in period
            if i["channel"] == "LinkedIn" and i["direction"] == "Outbound"
            and i["event_type"] not in ("Connection request sent",)
        ),
        "working_days": days,
    }


def delta(current, previous):
    """Écart avec la période précédente (None si une des deux valeurs manque)."""

    if current is None or previous is None:
        return None

    return round(current - previous, 1)


# ==========================================
# DÉTAILS
# ==========================================

def daily_activity(all_interactions, start, end):
    """Par jour : appels sortants, emails envoyés, réactions reçues."""

    period = in_range(all_interactions, start, end)
    rows = []

    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        items = [i for i in period if _day(i) == day]

        rows.append({
            "Day": day.isoformat(),
            "Calls": sum(1 for i in items if i["direction"] == "Outbound" and i["channel"] == "Call"),
            "Emails sent": sum(1 for i in items if i["direction"] == "Outbound" and i["channel"] == "Email"),
            "Replies": sum(1 for i in items if i["direction"] == "Inbound" and i["channel"] in REACTION_CHANNELS),
        })

    return rows


def by_vertical(all_interactions, objections, prospects, start, end):
    """Indicateurs par verticale (prospects contactés pendant la période)."""

    vertical_of = {p["id"]: p.get("vertical") or "Unknown" for p in prospects}
    groups = defaultdict(list)

    for item in all_interactions:
        groups[vertical_of.get(item["contact_id"], "Unknown")].append(item)

    objection_groups = defaultdict(list)
    for o in objections:
        objection_groups[vertical_of.get(o["contact_id"], "Unknown")].append(o)

    rows = []

    for vertical, items in groups.items():
        kpis = compute_kpis(items, objection_groups.get(vertical, []), start, end)

        if not kpis["contacted"] and not kpis["meetings"]:
            continue

        rows.append({
            "Vertical": vertical,
            "Prospects contacted": kpis["contacted"],
            "Calls": kpis["calls"],
            "Connection rate (%)": kpis["connection_rate"],
            "Emails sent": kpis["emails_sent"],
            "Reply rate (%)": kpis["reply_rate"],
            "Meetings": kpis["meetings"],
            "Conversion (%)": kpis["conversion_rate"],
            "Objections": kpis["objections"],
        })

    return sorted(rows, key=lambda r: (-r["Prospects contacted"], r["Vertical"]))


# ==========================================
# P2.3 : FAIBLE VOLUME ET FILTRE PAR COMMERCIAL
# ==========================================

# En dessous de cet échantillon, un taux est trop fragile pour être interprété
# (1 réponse sur 3 prospects = 33 %, mais cela ne veut encore rien dire).
MIN_SAMPLE = 10

# Taux -> (clé de l'échantillon, libellé du taux, unité au singulier, unité au pluriel)
RATE_SAMPLES = {
    "connection_rate": ("calls", "connection rate", "call", "calls"),
    "reply_rate": ("contacted", "reply rate", "prospect contacted", "prospects contacted"),
    "conversion_rate": ("contacted", "conversion rate", "prospect contacted", "prospects contacted"),
    "linkedin_acceptance_rate": ("invited", "acceptance rate", "prospect invited", "prospects invited"),
}


def low_volume_rates(kpis, minimum=MIN_SAMPLE):
    """Taux calculés sur un échantillon trop petit pour être fiables.

    Retourne {clé du taux: texte}, par ex. {"reply_rate": "reply rate: 3 prospects contacted"}.
    Un taux absent (None, rien à diviser) n'est pas signalé : il s'affiche déjà « — ».
    """

    warnings = {}

    for rate, (sample_key, label, singular, plural) in RATE_SAMPLES.items():
        sample = kpis.get(sample_key) or 0

        if kpis.get(rate) is not None and sample < minimum:
            warnings[rate] = f"{label}: {sample} {singular if sample == 1 else plural}"

    return warnings


UNASSIGNED = "Unassigned"


def owner_options(prospects):
    """Commerciaux proposés dans le filtre (propriétaires des prospects), puis « Unassigned »."""

    owners = sorted({p["owner"] for p in prospects if p.get("owner")})

    return owners + ([UNASSIGNED] if any(not p.get("owner") for p in prospects) else [])


def filter_by_owner(items, prospects, owners):
    """Garde les éléments (interactions, objections, prospects) des prospects des commerciaux choisis.

    Le commercial est celui du PROSPECT (contacts.owner) : REVORA n'enregistre pas
    encore qui a réalisé chaque interaction (multi-utilisateur : phase 11).
    owners vide = aucun filtre.
    """

    if not owners:
        return items

    owner_of = {p["id"]: p.get("owner") or UNASSIGNED for p in prospects}
    key = "contact_id" if items and "contact_id" in items[0] else "id"

    return [item for item in items if owner_of.get(item[key]) in owners]
