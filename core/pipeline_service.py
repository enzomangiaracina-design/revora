"""Service pipeline : tableau Kanban, inactivité et priorités.

La PRIORITÉ calculée ici mesure l'URGENCE (que faire maintenant ?), en
complément du score (core/scoring.py) qui mesure le potentiel ; à égalité
d'urgence, le meilleur score passe devant. Elle ne repose que sur des
faits enregistrés (relances, dates d'interaction, étape) et chaque prospect
affiche les raisons de sa priorité. Le nombre de contacts n'augmente jamais
la priorité : un prospect très sollicité n'est pas "meilleur" pour autant.
"""

from datetime import date, datetime, timedelta

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


# ==========================================
# TABLEAU FAÇON HUBSPOT : CARTES, TRIS, FILTRES RAPIDES
# ==========================================

SORT_OPTIONS = [
    "Last activity (most recent)",
    "Create date (newest)",
    "Score (highest)",
    "Next follow-up (soonest)",
    "Company (A–Z)",
]

CREATED_FILTERS = ["Any time", "Today", "Last 7 days", "Last 30 days"]
ACTIVITY_FILTERS = ["Any time", "Last 7 days", "Last 30 days", "Inactive", "Never contacted"]
FOLLOW_UP_FILTERS = ["Any", "Overdue", "Due today", "Next 7 days", "None scheduled"]

_PERIOD_DAYS = {"Today": 0, "Last 7 days": 6, "Last 30 days": 29}


def format_date(value):
    """"2026-11-14 10:05:00" ou "2026-11-14" -> "14/11/2026" ; vide -> None."""

    if not value:
        return None

    return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")


def initials(first_name, last_name):
    """Initiales affichées dans l'avatar ("Thomas", "Martins" -> "TM")."""

    letters = [(name or "").strip()[:1] for name in (first_name, last_name)]

    return "".join(letters).upper() or "?"


def filter_quick(prospects, summaries, created="Any time", activity="Any time",
                 follow_up="Any", stale_days=DEFAULT_STALE_DAYS, today=None):
    """Filtres rapides par dates (création, dernière activité, prochaine relance).

    Les dates de création sont attendues en heure LOCALE (created_at_local).
    """

    today = today or date.today()
    results = []

    for prospect in prospects:
        summary = summaries.get(prospect["id"], {})

        if created in _PERIOD_DAYS:
            created_day = (prospect.get("created_at_local") or prospect.get("created_at") or "")[:10]
            if not created_day or (today - date.fromisoformat(created_day)).days > _PERIOD_DAYS[created]:
                continue

        days = days_since(summary.get("last_interaction_at"), today)

        if activity in _PERIOD_DAYS and (days is None or days > _PERIOD_DAYS[activity]):
            continue
        if activity == "Inactive" and not (days is None or days >= stale_days):
            continue
        if activity == "Never contacted" and days is not None:
            continue

        due = (summary.get("next_task_due") or "")[:10]
        today_iso = today.isoformat()

        if follow_up == "Overdue" and not (due and due < today_iso):
            continue
        if follow_up == "Due today" and due != today_iso:
            continue
        if follow_up == "Next 7 days" and not (
            due and today_iso <= due <= (today + timedelta(days=7)).isoformat()
        ):
            continue
        if follow_up == "None scheduled" and summary.get("next_task_title"):
            continue

        results.append(prospect)

    return results


def sort_prospects(prospects, sort_by, summaries, scores):
    """Trie les prospects selon une option de SORT_OPTIONS.

    Les valeurs manquantes (jamais contacté, aucune relance) vont à la fin.
    """

    def summary(p):
        return summaries.get(p["id"], {})

    if sort_by == "Create date (newest)":
        return sorted(prospects, key=lambda p: p.get("created_at") or "", reverse=True)

    if sort_by == "Score (highest)":
        return sorted(prospects, key=lambda p: (scores.get(p["id"], {}) or {}).get("global", 0), reverse=True)

    if sort_by == "Next follow-up (soonest)":
        return sorted(prospects, key=lambda p: (summary(p).get("next_task_due") is None,
                                                summary(p).get("next_task_due") or ""))

    if sort_by == "Company (A–Z)":
        return sorted(prospects, key=lambda p: ((p.get("company_name") or "").casefold(),
                                                (p.get("last_name") or "").casefold()))

    # Par défaut : dernière activité la plus récente d'abord, jamais contactés à la fin
    with_activity = [p for p in prospects if summary(p).get("last_interaction_at")]
    without = [p for p in prospects if not summary(p).get("last_interaction_at")]

    return sorted(with_activity, key=lambda p: summary(p)["last_interaction_at"], reverse=True) + without


def build_card(prospect, summary, score, stale_days=DEFAULT_STALE_DAYS, today=None):
    """Données d'une carte du tableau (format attendu par ui/kanban.py)."""

    today = today or date.today()
    summary = summary or {}
    days = days_since(summary.get("last_interaction_at"), today)
    due = summary.get("next_task_due")

    if summary.get("next_task_title"):
        next_follow_up = f"{format_date(due) or 'no date'} · {summary['next_task_title']}"
    else:
        next_follow_up = "None scheduled"

    return {
        "id": prospect["id"],
        "title": prospect.get("company_name") or "No company",
        "contact": f"{prospect.get('first_name') or ''} {prospect.get('last_name') or ''}".strip(),
        "initials": initials(prospect.get("first_name"), prospect.get("last_name")),
        "created": format_date(prospect.get("created_at_local") or prospect.get("created_at")) or "—",
        "last_activity": (
            "Never contacted" if days is None
            else f"{format_date(summary['last_interaction_at'])} ({days} d ago)"
        ),
        "stale": days is None or days >= stale_days,
        "next_follow_up": next_follow_up,
        "overdue": bool(due) and due[:10] < today.isoformat(),
        "owner": prospect.get("owner") or "Unassigned",
        "score": (score or {}).get("global", 0),
        "temperature": (score or {}).get("temperature", "Cold"),
    }
