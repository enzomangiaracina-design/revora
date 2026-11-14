"""Service activités — emplacement réservé (phase 3).

Rôle prévu : enregistrer et lire les interactions (appels, emails, notes,
LinkedIn) et les relances, quelle que soit leur source (saisie manuelle ou
connecteur), en garantissant qu'une même interaction n'est stockée qu'une
seule fois (contrainte UNIQUE(provider, external_id) de la table interactions).

Pour l'instant, main.py continue d'appeler database.py directement.
"""
