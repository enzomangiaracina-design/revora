"""Service activités : enregistrement des interactions et suivi des relances.

Rôle : enregistrer et lire les interactions (appels, emails, LinkedIn, notes)
et les relances, entre l'interface (main.py) et la base (database.py).

Pour l'instant, seules les saisies manuelles existent (provider = "manual").
Les connecteurs (HubSpot, Gmail, Noota…) passeront plus tard par ce même
service, avec la contrainte UNIQUE(provider, external_id) qui empêche
d'enregistrer deux fois la même interaction.
"""

from datetime import date, datetime, timedelta

import database

CHANNELS = ["Call", "Email", "LinkedIn", "Note"]

DIRECTIONS = ["Outbound", "Inbound", "Internal"]

RESULTS = [
    "Completed",
    "No answer",
    "Voicemail",
    "Positive response",
    "Objection",
    "Meeting booked",
    "Information shared",
    "Other",
]

TASK_OPEN = "A faire"
TASK_DONE = "Terminee"

PERIODS = ["Today", "Last 7 days", "Last 30 days", "All time"]


# ==========================================
# ENREGISTREMENT D'UNE INTERACTION
# ==========================================

def log_interaction(contact_id, data, now=None):
    """Valide puis enregistre une interaction, et crée la relance si demandée.

    `data` contient : channel, direction, event_type, subject, content,
    outcome, occurred_at (datetime locale), duration_minutes (appels),
    follow_up_date (date optionnelle), objection_category et
    objection_verbatim (optionnels : objection exprimée pendant l'échange).

    Retourne (succès, message).
    """

    now = now or datetime.now()

    subject = (data.get("subject") or "").strip()
    content = (data.get("content") or "").strip()
    outcome = (data.get("outcome") or "").strip()
    occurred_at = data.get("occurred_at") or now
    follow_up_date = data.get("follow_up_date")

    if data.get("channel") not in CHANNELS:
        return False, "Type d'interaction inconnu."

    if not subject and not content:
        return False, "Saisissez un objet ou une note."

    # Une marge d'une minute couvre l'écart entre l'heure affichée et le clic
    if occurred_at > now + timedelta(minutes=1):
        return False, "La date de l'interaction ne peut pas être dans le futur."

    if follow_up_date and follow_up_date < occurred_at.date():
        return False, "La date de relance doit être postérieure à l'interaction."

    metadata = {}
    duration = data.get("duration_minutes") or 0

    if data["channel"] == "Call" and duration > 0:
        metadata["duration_seconds"] = int(duration * 60)

    interaction_id = database.add_interaction(
        contact_id,
        data["channel"],
        data.get("direction"),
        data.get("event_type") or "Other",
        subject,
        content,
        outcome,
        occurred_at=occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
        metadata=metadata or None,
    )

    done = ["Interaction enregistrée"]

    objection = (data.get("objection_category") or "").strip()

    if objection:
        database.add_objection(
            contact_id,
            objection,
            verbatim=data.get("objection_verbatim"),
            interaction_id=interaction_id,
            occurred_at=occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        done.append(f"objection « {objection} » notée")

    if follow_up_date:
        title = outcome or f"Follow up after {data['channel'].lower()}"
        database.create_task(contact_id, title, content, follow_up_date.isoformat())
        done.append("relance planifiée")

    return True, ", ".join(done) + "."


# ==========================================
# RELANCES
# ==========================================

def group_tasks(tasks, today=None):
    """Range les relances par échéance.

    Retourne un dictionnaire avec les clés :
    overdue (en retard), today, upcoming (à venir), no_date, done.
    """

    today = (today or date.today()).isoformat()

    groups = {"overdue": [], "today": [], "upcoming": [], "no_date": [], "done": []}

    for task in tasks:
        due = (task.get("due_at") or "")[:10]

        if task.get("status") != TASK_OPEN:
            groups["done"].append(task)
        elif not due:
            groups["no_date"].append(task)
        elif due < today:
            groups["overdue"].append(task)
        elif due == today:
            groups["today"].append(task)
        else:
            groups["upcoming"].append(task)

    return groups


# ==========================================
# PERIODES ET COMPTEURS
# ==========================================

def period_bounds(period, today=None):
    """Retourne (date_début, date_fin) au format "AAAA-MM-JJ" pour une période.

    "All time" retourne (None, None) : pas de limite.
    """

    today = today or date.today()

    if period == "Today":
        start = today
    elif period == "Last 7 days":
        start = today - timedelta(days=6)
    elif period == "Last 30 days":
        start = today - timedelta(days=29)
    else:
        return None, None

    return start.isoformat(), today.isoformat()


def count_by_channel(interactions):
    """Compte les interactions par canal (tous les canaux connus, même à 0)."""

    counts = {channel: 0 for channel in CHANNELS}

    for item in interactions:
        counts[item["channel"]] = counts.get(item["channel"], 0) + 1

    return counts


def format_duration(metadata):
    """Durée d'appel lisible ("5 min 30 s"), ou chaîne vide si inconnue."""

    seconds = (metadata or {}).get("duration_seconds")

    if not seconds:
        return ""

    minutes, seconds = divmod(int(seconds), 60)

    return f"{minutes} min {seconds} s" if seconds else f"{minutes} min"
