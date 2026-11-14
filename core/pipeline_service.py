"""Service pipeline : tableau Kanban, inactivité et priorités.

La PRIORITÉ calculée ici mesure l'URGENCE (que faire maintenant ?), en
complément du score (core/scoring.py) qui mesure le potentiel ; à égalité
d'urgence, le meilleur score passe devant. Elle ne repose que sur des
faits enregistrés (relances, dates d'interaction, étape) et chaque prospect
affiche les raisons de sa priorité. Le nombre de contacts n'augmente jamais
la priorité : un prospect très sollicité n'est pas "meilleur" pour autant.
"""

from datetime import date, datetime

# Points attribués par raison (provisoire, à calibrer)
POINTS = {
    "overdue": 3,         # relance en retard
    "due_today": 2,       # relance prévue aujourd'hui
    "never_contacted": 1, # aucune interaction enregistrée
    "stale": 1,           # pas d'interaction depuis N jours
}

DEFAULT_STALE_DAYS = 14


def days_since(last_interaction_at, today=None):
    """Nombre de jours depuis la dernière interaction ("AAAA-MM-JJ HH:MM:SS" locale).

    Retourne None si le prospect n'a jamais eu d'interaction.
    """

    if not last_interaction_at:
        return None

    today = today or date.today()
    last_day = datetime.fromisoformat(last_interaction_at).date()

    return (today - last_day).days


def is_stale(summary, stale_days=DEFAULT_STALE_DAYS, today=None):
    """Vrai si le prospect n'a aucune interaction depuis `stale_days` jours (ou jamais)."""

    days = days_since((summary or {}).get("last_interaction_at"), today)

    return days is None or days >= stale_days


def build_board(prospects, stages):
    """Range les prospects par étape. Retourne {nom_étape: [prospects]}.

    Les étapes vides sont présentes avec une liste vide. Un prospect dont
    le statut n'existe pas (cas anormal) est rangé dans la première étape
    plutôt que d'être masqué.
    """

    board = {stage["name"]: [] for stage in stages}
    first = stages[0]["name"] if stages else None

    for prospect in prospects:
        stage = prospect.get("status")
        board.setdefault(stage if stage in board else first, []).append(prospect)

    return board


def prioritize(
    prospects, stages, summaries, stale_days=DEFAULT_STALE_DAYS, today=None, scores=None
):
    """Classe les prospects des étapes ouvertes par priorité décroissante.

    Retourne une liste de dictionnaires :
    {"prospect": ..., "points": n, "reasons": [...], "summary": {...}}.
    Seuls les prospects ayant au moins une raison sont retournés.
    À égalité de points : le score global le plus élevé (si `scores`
    {contact_id: score} est fourni), puis l'étape la plus avancée.
    """

    today = today or date.today()
    scores = scores or {}
    today_iso = today.isoformat()

    open_positions = {
        stage["name"]: index for index, stage in enumerate(stages) if not stage["is_closed"]
    }

    ranked = []

    for prospect in prospects:
        if prospect.get("status") not in open_positions:
            continue

        summary = summaries.get(prospect["id"], {})
        reasons = []
        points = 0

        due = (summary.get("next_task_due") or "")[:10]

        if due and due < today_iso:
            reasons.append(f"Overdue follow-up ({due}): {summary.get('next_task_title')}")
            points += POINTS["overdue"]
        elif due == today_iso:
            reasons.append(f"Follow-up due today: {summary.get('next_task_title')}")
            points += POINTS["due_today"]

        days = days_since(summary.get("last_interaction_at"), today)

        if days is None:
            reasons.append("Never contacted")
            points += POINTS["never_contacted"]
        elif days >= stale_days:
            reasons.append(f"No activity for {days} days")
            points += POINTS["stale"]

        if reasons:
            ranked.append({
                "prospect": prospect,
                "points": points,
                "reasons": reasons,
                "summary": summary,
            })

    ranked.sort(
        key=lambda item: (
            item["points"],
            scores.get(item["prospect"]["id"], 0),
            open_positions[item["prospect"]["status"]],
        ),
        reverse=True,
    )

    return ranked
