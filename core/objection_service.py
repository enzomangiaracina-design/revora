"""Objection Intelligence : saisie, statistiques, exemples anonymisés, préparation d'appel.

Règle du cahier des charges : ne JAMAIS inventer une objection qui n'a pas
été exprimée. Pour l'instant, seules les objections saisies par le
commercial existent (source "manual"). La détection automatique par IA
viendra plus tard et devra toujours être confirmée par le commercial.

Les réponses recommandées sont rédigées par le commercial lui-même
(onglet Playbook) : REVORA ne les invente pas.
"""

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import database

# Catégories du cahier des charges (on peut en ajouter de nouvelles à la saisie)
DEFAULT_CATEGORIES = [
    "No budget",
    "Bad timing",
    "Already equipped",
    "Not interested",
    "Lack of resources",
    "Needs internal approval",
    "Not the decision maker",
    "Different priorities",
    "Price too high",
    "Competitor solution",
]

STATUSES = ["Open", "Handled", "Lost"]

PLAYBOOK_PLACEHOLDER = (
    "1. Acknowledge: show you heard the concern.\n"
    "2. Clarify: ask one question to understand the real reason.\n"
    "3. Respond: one fact, proof or customer example.\n"
    "4. Next step: propose a concrete, small commitment."
)

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_PATTERN = re.compile(r"(?<!\w)(\+?\d[\d .\-()]{7,}\d)(?!\w)")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


# ==========================================
# SAISIE
# ==========================================

def categories(objections=None):
    """Catégories proposées : celles par défaut, puis celles déjà utilisées."""

    used = sorted({o["category"] for o in (objections or [])} - set(DEFAULT_CATEGORIES))

    return DEFAULT_CATEGORIES + used


def record_objection(contact_id, category, verbatim=None, *, interaction_id=None, occurred_at=None):
    """Valide puis enregistre une objection. Retourne (succès, message).

    Concept : l'étoile (*) rend interaction_id et occurred_at "nommés
    obligatoirement" : record_objection(1, "No budget", "…", occurred_at=…).
    Impossible de passer une date à la place d'un identifiant par erreur.
    """

    category = (category or "").strip()

    if not category:
        return False, "Choisissez une catégorie d'objection."

    database.add_objection(
        contact_id,
        category,
        verbatim=verbatim,
        interaction_id=interaction_id,
        occurred_at=occurred_at.strftime("%Y-%m-%d %H:%M:%S") if occurred_at else None,
    )

    return True, f"Objection enregistrée : {category}."


# ==========================================
# STATISTIQUES
# ==========================================

def count_by(objections, field):
    """[(valeur, nombre)] trié par nombre décroissant puis par valeur."""

    counts = Counter((o.get(field) or "Unknown") for o in objections)

    return sorted(counts.items(), key=lambda item: (-item[1], str(item[0]).casefold()))


def filter_period(objections, days=None, today=None):
    """Objections des `days` derniers jours (None = toutes)."""

    if days is None:
        return list(objections)

    start = ((today or date.today()) - timedelta(days=days - 1)).isoformat()

    return [o for o in objections if (o.get("occurred_at_local") or "")[:10] >= start]


def week_start(day_iso):
    """Lundi de la semaine d'une date "AAAA-MM-JJ"."""

    day = date.fromisoformat(day_iso[:10])

    return (day - timedelta(days=day.weekday())).isoformat()


def weekly_trend(objections):
    """{semaine (lundi): {catégorie: nombre}} trié par semaine."""

    trend = defaultdict(Counter)

    for o in objections:
        if o.get("occurred_at_local"):
            trend[week_start(o["occurred_at_local"])][o["category"]] += 1

    return {week: dict(trend[week]) for week in sorted(trend)}


def resolution_by_category(objections):
    """Par catégorie : total, traitées, perdues, ouvertes et taux de traitement (%)."""

    rows = []

    for category, total in count_by(objections, "category"):
        items = [o for o in objections if o["category"] == category]
        handled = sum(1 for o in items if o["status"] == "Handled")
        lost = sum(1 for o in items if o["status"] == "Lost")

        rows.append({
            "Category": category,
            "Total": total,
            "Handled": handled,
            "Lost": lost,
            "Open": total - handled - lost,
            "Handled rate (%)": round(handled / total * 100),
        })

    return rows


# ==========================================
# EXEMPLES ANONYMISÉS
# ==========================================

def anonymize(text, objection):
    """Retire d'une formulation les éléments qui identifient le prospect.

    Remplace : nom, prénom, entreprise, emails, numéros de téléphone, liens.
    """

    if not text:
        return text

    result = EMAIL_PATTERN.sub("[email]", text)
    result = URL_PATTERN.sub("[link]", result)
    result = PHONE_PATTERN.sub("[phone]", result)

    replacements = [
        (objection.get("company_name"), "[company]"),
        (objection.get("first_name"), "[contact]"),
        (objection.get("last_name"), "[contact]"),
    ]

    for value, label in replacements:
        value = (value or "").strip()

        if len(value) >= 2:
            result = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", label, result, flags=re.IGNORECASE)

    return re.sub(r"(\[contact\]\s*){2,}", "[contact] ", result).strip()


def anonymized_examples(objections, category, limit=5):
    """Formulations anonymisées, distinctes, les plus récentes d'abord."""

    examples = []

    for o in objections:
        if o["category"] != category or not o.get("verbatim"):
            continue

        text = anonymize(o["verbatim"], o)

        if text and text not in examples:
            examples.append(text)

        if len(examples) >= limit:
            break

    return examples


# ==========================================
# PRÉPARATION D'APPEL
# ==========================================

def call_preparation(contact_id):
    """Objections déjà exprimées par ce prospect + réponses du playbook.

    Retourne une liste triée (ouvertes d'abord) :
    [{"category", "count", "open", "last_seen", "verbatims", "response"}].
    """

    objections = database.get_objections(contact_id)
    responses = database.get_objection_responses()
    grouped = defaultdict(list)

    for o in objections:
        grouped[o["category"]].append(o)

    prep = []

    for category, items in grouped.items():
        prep.append({
            "category": category,
            "count": len(items),
            "open": sum(1 for o in items if o["status"] == "Open"),
            "last_seen": max((o.get("occurred_at_local") or "") for o in items)[:10],
            "verbatims": [o["verbatim"] for o in items if o.get("verbatim")][:3],
            "response": responses.get(category),
        })

    return sorted(prep, key=lambda p: (-p["open"], -p["count"], p["category"]))


def format_day(value):
    """"2026-11-14 10:00:00" -> "14/11/2026"."""

    return datetime.fromisoformat(value[:10]).strftime("%d/%m/%Y") if value else ""
