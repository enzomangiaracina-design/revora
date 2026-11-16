"""Journal d'événements (phase 13, fondations de REVORA MEMORY).

Principe : chaque décision utile à la future mémoire est notée — qui, quoi,
quand, sur quel objet. Le journal ne fait qu'AJOUTER des lignes : rien n'y est
modifié ni supprimé, et rien n'est encore « appris » à partir de lui.

Les actions autorisées sont listées dans ACTIONS : un nom inconnu est refusé,
pour que le journal reste lisible et exploitable plus tard.
"""

import database

# Nom de l'action -> type d'objet concerné
ACTIONS = {
    "ai_objection_accepted": "objection",     # suggestion IA ajoutée par le commercial (Add)
    "ai_objection_dismissed": None,           # suggestion IA refusée (Dismiss) : rien n'est créé
    "ai_draft_kept": "interaction",           # brouillon d'email IA gardé en note
    "task_completed": "task",                 # relance marquée comme faite
}


def record(action, user_id=None, *, object_id=None, contact_id=None, details=None):
    """Note une action dans le journal. Retourne l'identifiant de l'événement.

    user_id : users.id de la personne active (None si l'équipe est vide).
    details : petit dictionnaire (ex. {"category": "No budget"}). Jamais d'email,
              de téléphone ni de secret.
    """

    if action not in ACTIONS:
        raise ValueError(f"Unknown activity event: {action}")

    return database.add_activity_event(
        action, user_id, ACTIONS[action], object_id, contact_id, details
    )


def history(user_id=None, contact_id=None, action=None, limit=100):
    """Événements du journal, du plus récent au plus ancien."""

    return database.get_activity_events(user_id=user_id, contact_id=contact_id, action=action, limit=limit)
