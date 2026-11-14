"""Service prospects — emplacement réservé (phase 2).

Rôle prévu : regrouper les règles métier sur les prospects et entreprises
(création, modification, suppression avec confirmation, import CSV, détection
de doublons, filtres), entre l'interface (main.py) et la base (database.py).

Pour l'instant, main.py continue d'appeler database.py directement : rien n'a
été déplacé. Les fonctions seront ajoutées ici au fur et à mesure de la phase 2,
avec leurs tests dans tests/test_prospects.py.
"""
