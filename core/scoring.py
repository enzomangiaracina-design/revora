"""Moteur de scoring de REVORA.

Trois dimensions, chacune sur 100 :
  - FIT        : le prospect correspond-il à la cible (profil client idéal) ?
  - ENGAGEMENT : le prospect interagit-il réellement avec nous ?
  - INTENT     : a-t-il une intention d'achat confirmée ou observée ?

Score global = moyenne pondérée (0,35 Fit + 0,40 Engagement + 0,25 Intent par défaut).

Principes (cahier des charges) :
  - Chaque point est expliqué et typé :
      "observed"  = signal observé dans les interactions enregistrées,
      "confirmed" = information confirmée par le commercial,
      "rule"      = règle appliquée (plafond, étape fermée…).
    Aucun signal n'est "inféré par l'IA" pour l'instant.
  - Le nombre de tentatives n'apporte AUCUN point : 10 appels sans réponse
    ne rendent pas un prospect plus chaud. Seules les réactions du prospect
    (réponses, appels entrants, conversations) comptent.
  - Plafonds par type de signal et décroissance temporelle : un signal ancien
    pèse moins qu'un signal récent (demi-vie configurable).
  - Si la cible (Fit) n'est pas configurée, le Fit est "non évalué" et le score
    global est calculé sur les dimensions disponibles, au lieu d'inventer une valeur.

Toutes les valeurs ci-dessous sont PROVISOIRES et devront être calibrées.

Ce module est "pur" : il ne lit ni n'écrit la base. Il reçoit des données et
retourne des résultats, ce qui le rend simple à tester.
"""

from copy import deepcopy
from datetime import date, datetime

# Pondérations indicatives du cahier des charges (leur somme doit valoir 1).
DEFAULT_WEIGHTS = {
    "fit": 0.35,
    "engagement": 0.40,
    "intent": 0.25,
}

DEFAULT_CONFIG = {
    "weights": dict(DEFAULT_WEIGHTS),
    "thresholds": {"hot": 70, "warm": 40},
    "half_life_days": 30,
    "icp": {
        "verticals": [],       # verticales cibles (vide = critère non utilisé)
        "title_keywords": [],  # mots-clés de poste cibles, ex. "sales", "ceo"
    },
}

# ---------- Engagement : réactions du prospect (signaux observés) ----------
# Chaque règle : (clé, libellé, points par interaction, plafond total, condition)

CONVERSATION_RESULTS = {
    "Completed", "Positive response", "Objection", "Meeting booked", "Information shared",
}

ENGAGEMENT_RULES = [
    ("inbound_email", "Email reply / inbound email", 20, 40,
     lambda i: i["direction"] == "Inbound" and i["channel"] == "Email"),
    ("inbound_call", "Inbound call", 25, 50,
     lambda i: i["direction"] == "Inbound" and i["channel"] == "Call"),
    ("inbound_linkedin", "LinkedIn reply / inbound message", 15, 30,
     lambda i: i["direction"] == "Inbound" and i["channel"] == "LinkedIn"),
    ("conversation", "Phone conversation", 15, 45,
     lambda i: i["direction"] == "Outbound" and i["channel"] == "Call"
     and i["event_type"] in CONVERSATION_RESULTS),
    ("positive_response", "Positive response", 20, 40,
     lambda i: i["event_type"] == "Positive response"),
]

# ---------- Intent ----------
# Informations confirmées par le commercial (fiche prospect > Qualification)
INTENT_CONFIRMED = [
    ("need_identified", "Need identified", 25),
    ("is_decision_maker", "Talking to the decision maker", 15),
    ("budget_confirmed", "Budget confirmed", 30),
    ("demo_requested", "Demo requested", 30),
]

# Signal observé : réunion obtenue (dans le résultat d'une interaction)
MEETING_POINTS = 35


# ==========================================
# OUTILS
# ==========================================

def merge_config(config=None):
    """Complète une configuration partielle avec les valeurs par défaut."""

    merged = deepcopy(DEFAULT_CONFIG)

    for key, value in (config or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value

    return merged


def validate_config(config):
    """Retourne la liste des erreurs d'une configuration (vide si valide)."""

    errors = []
    weights = config["weights"]

    if set(weights) != {"fit", "engagement", "intent"}:
        errors.append("Les pondérations doivent contenir fit, engagement et intent.")
    elif abs(sum(weights.values()) - 1) > 1e-6 or min(weights.values()) < 0:
        errors.append("Les pondérations doivent être positives et totaliser 100 %.")

    hot, warm = config["thresholds"]["hot"], config["thresholds"]["warm"]
    if not 0 < warm < hot <= 100:
        errors.append("Les seuils doivent respecter 0 < Warm < Hot ≤ 100.")

    if config["half_life_days"] <= 0:
        errors.append("La demi-vie doit être supérieure à 0 jour.")

    return errors


def decay(age_days, half_life_days):
    """Poids d'un signal selon son âge : 1 aujourd'hui, 0,5 après une demi-vie, etc."""

    return 0.5 ** (max(age_days, 0) / half_life_days)


def _age_days(interaction, today):
    return (today - datetime.fromisoformat(interaction["occurred_at_local"]).date()).days


def _day(interaction):
    return interaction["occurred_at_local"][:10]


# ==========================================
# DIMENSIONS
# ==========================================

def compute_fit(prospect, config):
    """Fit Score : correspondance avec la cible configurée.

    Retourne (score ou None si aucun critère configuré, explications).
    """

    icp = config["icp"]
    explanation = []
    possible = earned = 0

    verticals = [v.strip().casefold() for v in icp.get("verticals", []) if v.strip()]
    if verticals:
        possible += 50
        vertical = (prospect.get("vertical") or "").strip()

        if vertical.casefold() in verticals:
            earned += 50
            explanation.append(_item("fit", f"Target vertical: {vertical}", 50, "confirmed"))
        else:
            explanation.append(_item("fit", f"Vertical outside target: {vertical or 'unknown'}", 0, "confirmed"))

    keywords = [k.strip().casefold() for k in icp.get("title_keywords", []) if k.strip()]
    if keywords:
        possible += 50
        title = (prospect.get("job_title") or "").strip()
        matched = [k for k in keywords if k in title.casefold()]

        if matched:
            earned += 50
            explanation.append(_item("fit", f"Target job title: {title} ({', '.join(matched)})", 50, "confirmed"))
        else:
            explanation.append(_item("fit", f"Job title outside target: {title or 'unknown'}", 0, "confirmed"))

    if not possible:
        return None, [_item("fit", "Target profile not configured: Fit not evaluated", 0, "rule")]

    return round(earned / possible * 100), explanation


def compute_engagement(interactions, config, today):
    """Engagement Score : réactions du prospect, pondérées par leur fraîcheur et plafonnées."""

    half_life = config["half_life_days"]
    explanation = []
    total = 0

    for key, label, points, cap, condition in ENGAGEMENT_RULES:
        matching = sorted(
            (i for i in interactions if condition(i)),
            key=lambda i: i["occurred_at_local"],
            reverse=True,
        )

        rule_total = 0

        for interaction in matching:
            weighted = points * decay(_age_days(interaction, today), half_life)
            remaining = cap - rule_total

            if remaining <= 0:
                explanation.append(_item(
                    "engagement", f"{label} ({_day(interaction)}): cap of {cap} reached", 0, "rule"
                ))
                continue

            gained = min(weighted, remaining)
            rule_total += gained
            explanation.append(_item(
                "engagement", f"{label} ({_day(interaction)})", round(gained, 1), "observed"
            ))

        total += rule_total

    attempts = sum(
        1 for i in interactions
        if i["direction"] == "Outbound" and not any(rule[4](i) for rule in ENGAGEMENT_RULES)
    )

    if attempts:
        explanation.append(_item(
            "engagement", f"{attempts} outbound attempt(s) without reaction: no points by design", 0, "rule"
        ))

    return min(round(total), 100), explanation


def compute_intent(prospect, interactions, config, today, stage_closed=False):
    """Intent Score : qualification confirmée + réunion obtenue (observée)."""

    explanation = []

    if stage_closed:
        return 0, [_item(
            "intent", f"Closed stage ({prospect.get('status')}): intent set to 0", 0, "rule"
        )]

    total = 0

    for field, label, points in INTENT_CONFIRMED:
        if prospect.get(field):
            total += points
            explanation.append(_item("intent", label, points, "confirmed"))

    meetings = sorted(
        (i for i in interactions if i["event_type"] == "Meeting booked"),
        key=lambda i: i["occurred_at_local"],
        reverse=True,
    )

    if meetings:
        latest = meetings[0]
        gained = MEETING_POINTS * decay(_age_days(latest, today), config["half_life_days"])
        total += gained
        explanation.append(_item(
            "intent", f"Meeting booked ({_day(latest)})", round(gained, 1), "observed"
        ))

    return min(round(total), 100), explanation


# ==========================================
# SCORE GLOBAL
# ==========================================

def compute_global_score(fit, engagement, intent, weights=None):
    """Score global (sur 100) à partir des trois dimensions.

    `fit` peut valoir None (cible non configurée) : le score est alors la
    moyenne pondérée des dimensions disponibles.
    Retourne un nombre arrondi à 1 décimale.
    """

    weights = weights or DEFAULT_WEIGHTS

    if set(weights) != {"fit", "engagement", "intent"}:
        raise ValueError("Les pondérations doivent contenir fit, engagement et intent.")

    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("La somme des pondérations doit être égale à 1.")

    scores = {"fit": fit, "engagement": engagement, "intent": intent}

    for name, value in scores.items():
        if value is None and name == "fit":
            continue
        _check_score(name, value)

    available = {name: value for name, value in scores.items() if value is not None}
    weight_total = sum(weights[name] for name in available)

    if weight_total == 0:
        return 0.0

    total = sum(weights[name] * value for name, value in available.items()) / weight_total

    return round(total, 1)


def _check_score(name, value):
    """Vérifie qu'un score est un nombre compris entre 0 et 100."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"Le score {name} doit être un nombre.")

    if not 0 <= value <= 100:
        raise ValueError(f"Le score {name} doit être compris entre 0 et 100.")


def temperature(global_score, config=None):
    """Hot / Warm / Cold selon les seuils configurés."""

    thresholds = merge_config(config)["thresholds"]

    if global_score >= thresholds["hot"]:
        return "Hot"
    if global_score >= thresholds["warm"]:
        return "Warm"
    return "Cold"


def compute_scores(prospect, interactions, config=None, stage_closed=False, today=None):
    """Calcule les trois dimensions, le score global et leur explication.

    prospect     : dictionnaire (vertical, job_title, status, champs de qualification).
    interactions : interactions du prospect (avec occurred_at_local).
    """

    config = merge_config(config)
    today = today or date.today()

    fit, fit_explanation = compute_fit(prospect, config)
    engagement, engagement_explanation = compute_engagement(interactions, config, today)
    intent, intent_explanation = compute_intent(prospect, interactions, config, today, stage_closed)

    global_score = round(compute_global_score(fit, engagement, intent, config["weights"]))

    return {
        "fit": fit,
        "engagement": engagement,
        "intent": intent,
        "global": global_score,
        "temperature": temperature(global_score, config),
        "explanation": fit_explanation + engagement_explanation + intent_explanation,
    }


def _item(dimension, signal, points, kind):
    return {"dimension": dimension, "signal": signal, "points": points, "type": kind}
