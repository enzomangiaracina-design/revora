"""LinkedIn — AUCUN connecteur, par choix (phase 9).

Vérifié dans la documentation officielle (voir docs/LINKEDIN.md) :
  - aucune API ouverte ne donne accès aux relations, à la messagerie ni aux
    profils d'autres membres ;
  - l'API Sales Navigator (SNAP) est réservée aux partenaires et fermée aux
    nouveaux partenaires ;
  - les conditions d'utilisation interdisent scraping, robots, extensions et
    toute automatisation.

REVORA gère donc LinkedIn par saisie manuelle : URL du profil sur le prospect
et actions LinkedIn dans le formulaire d'interaction (core/activity_service.py).
"""
