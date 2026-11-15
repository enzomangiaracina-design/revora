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

# Actions propres à LinkedIn (saisies à la main : aucune automatisation, aucun
# accès à LinkedIn — interdit par ses conditions d'utilisation).
# Le sens est fixé par la nature de l'action.
LINKEDIN_RESULTS = {
    "Connection request sent": "Outbound",
    "Connection accepted": "Inbound",   # c'est le prospect qui agit
    "InMail sent": "Outbound",
}

RESULTS = RESULTS[:-1] + list(LINKEDIN_RESULTS) + ["Other"]

TASK_OPEN = "A faire"
TASK_DONE = "Terminee"

PERIODS = ["Today", "Last 7 days", "Last 30 days", "All time"]


# ==========================================
# ENREGISTREMENT D'UNE INTERACTION
# ==========================================

def _validate(data, now):
    """Vérifie une saisie d'interaction. Retourne (message d'erreur ou None, valeurs nettoyées).

    Partagée par l'enregistrement et la correction : les mêmes règles s'appliquent.
    """

    subject = (data.get("subject") or "").strip()
    content = (data.get("content") or "").strip()
    outcome = (data.get("outcome") or "").strip()
    occurred_at = data.get("occurred_at") or now
    follow_up_date = data.get("follow_up_date")

    if data.get("channel") not in CHANNELS:
        return "Type d'interaction inconnu.", None

    event_type = data.get("event_type") or "Other"
    direction = data.get("direction")

    if event_type in LINKEDIN_RESULTS:
        if data["channel"] != "LinkedIn":
            return f"« {event_type} » n'existe que pour le type LinkedIn.", None

        direction = LINKEDIN_RESULTS[event_type]
        # Une action LinkedIn se suffit à elle-même : l'objet est facultatif
        subject = subject or event_type

    if not subject and not content:
        return "Saisissez un objet ou une note.", None

    # Une marge d'une minute couvre l'écart entre l'heure affichée et le clic
    if occurred_at > now + timedelta(minutes=1):
        return "La date de l'interaction ne peut pas être dans le futur.", None

    if follow_up_date and follow_up_date < occurred_at.date():
        return "La date de relance doit être postérieure à l'interaction.", None

    metadata = {}
    duration = data.get("duration_minutes") or 0

    if data["channel"] == "Call" and duration > 0:
        metadata["duration_seconds"] = int(duration * 60)

    return None, {
        "channel": data["channel"], "direction": direction, "event_type": event_type,
        "subject": subject, "content": content, "outcome": outcome,
        "occurred_at": occurred_at.strftime("%Y-%m-%d %H:%M:%S"), "metadata": metadata or None,
    }


def log_interaction(contact_id, data, now=None):
    """Valide puis enregistre une interaction, et crée la relance si demandée.

    `data` contient : channel, direction, event_type, subject, content,
    outcome, occurred_at (datetime locale), duration_minutes (appels),
    follow_up_date (date optionnelle), objection_category et
    objection_verbatim (optionnels : objection exprimée pendant l'échange).

    Retourne (succès, message).
    """

    now = now or datetime.now()
    error, clean = _validate(data, now)

    if error:
        return False, error

    interaction_id = database.add_interaction(
        contact_id,
        clean["channel"],
        clean["direction"],
        clean["event_type"],
        clean["subject"],
        clean["content"],
        clean["outcome"],
        occurred_at=clean["occurred_at"],
        metadata=clean["metadata"],
    )

    done = ["Interaction enregistrée"]

    objection = (data.get("objection_category") or "").strip()

    if objection:
        database.add_objection(
            contact_id,
            objection,
            verbatim=data.get("objection_verbatim"),
            interaction_id=interaction_id,
            occurred_at=clean["occurred_at"],
        )
        done.append(f"objection « {objection} » notée")

    follow_up_date = data.get("follow_up_date")

    if follow_up_date:
        title = clean["outcome"] or f"Follow up after {data['channel'].lower()}"
        database.create_task(contact_id, title, clean["content"], follow_up_date.isoformat())
        done.append("relance planifiée")

    return True, ", ".join(done) + "."


def is_editable(interaction):
    """Une interaction se corrige seulement si elle a été saisie à la main."""

    return interaction.get("provider") in (None, "manual")


def edit_interaction(interaction_id, data, now=None):
    """Corrige une interaction saisie à la main (mêmes règles qu'à la saisie). Retourne (succès, message)."""

    current = database.get_interaction(interaction_id)

    if not current:
        return False, "Interaction introuvable."

    if not is_editable(current):
        return False, f"Cette interaction vient de {source_label(current['provider'])} : corrigez-la à la source."

    error, clean = _validate(data, now or datetime.now())

    if error:
        return False, error

    database.update_interaction(interaction_id, **clean)

    return True, "Interaction corrigée."


def remove_interaction(interaction_id):
    """Supprime une interaction saisie par erreur. Retourne (succès, message)."""

    current = database.get_interaction(interaction_id)

    if not current:
        return False, "Interaction introuvable."

    if not is_editable(current):
        return False, f"Cette interaction vient de {source_label(current['provider'])} : elle ne peut pas être supprimée ici."

    result = database.delete_interaction(interaction_id)
    message = "Interaction supprimée."

    if result["objections_unlinked"]:
        message += f" {result['objections_unlinked']} objection(s) conservée(s), sans lien vers cet échange."

    return True, message


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


# ==========================================
# P2.2 : SOURCE DES INTERACTIONS ET ÉTAT DES SYNCHRONISATIONS
# ==========================================

# Origine d'une interaction (colonne interactions.provider)
SOURCE_LABELS = {"manual": "Manual", "hubspot": "HubSpot", "gmail": "Gmail"}

# Connecteurs dont on affiche l'état (ordre d'affichage)
SYNC_PROVIDERS = [("hubspot", "HubSpot"), ("gmail", "Gmail")]


def source_label(provider):
    """Libellé lisible de l'origine d'une interaction ("manual" -> "Manual")."""

    return SOURCE_LABELS.get(provider, (provider or "manual").capitalize())


def source_options(interactions):
    """Sources proposées dans le filtre : les sources connues, puis toute autre présente."""

    known = list(SOURCE_LABELS.values())
    others = sorted({source_label(i.get("provider")) for i in interactions} - set(known))

    return known + others


def filter_by_source(interactions, labels):
    """Garde les interactions dont la source est dans labels (liste vide = tout)."""

    if not labels:
        return interactions

    return [i for i in interactions if source_label(i.get("provider")) in labels]


def sync_status(integrations, providers=SYNC_PROVIDERS):
    """État de chaque connecteur, tel qu'enregistré (rien n'est supposé).

    integrations : résultat de database.get_integrations().
    Retourne une liste de {"label", "state", "text"} ; state vaut
    "not_connected", "connected" ou "error".
    """

    lines = []

    for provider, label in providers:
        info = integrations.get(provider) or {}
        last_sync = info.get("last_sync_at")
        when = f"{last_sync[8:10]}/{last_sync[5:7]} {last_sync[11:16]}" if last_sync else None

        if info.get("status") == "Error":
            text = f"error: {info.get('last_error') or 'unknown'}"
            text += f" (last successful sync {when})" if when else " (never synced)"
            state = "error"
        elif when:
            text, state = f"last sync {when}", "connected"
        else:
            text, state = "not connected", "not_connected"

        lines.append({"label": label, "state": state, "text": text})

    return lines
