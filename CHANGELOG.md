# CHANGELOG — REVORA

## [0.3.1] — 2026-11-14

### Audit
- `main.py` importe 8 fonctions depuis `database.py` : les 8 existent dans le fichier actuel.
- `revora.db` : intégrité OK, 6 tables, 1 entreprise (AlphaEngine) et 1 contact (Thomas Martins).
- Cause de `ImportError: cannot import name 'get_prospect_by_id'` : l'erreur venait d'un lancement fait avec
  une ancienne version de `database.py` (le fichier actuel, enregistré plus tard, contient bien la fonction).
  Aucune modification de `database.py` n'était nécessaire.

### Modifié
- `main.py` : `use_container_width=True` remplacé par `width="stretch"` (3 occurrences) — option dépréciée par Streamlit.

### Ajouté
- `README.md`, `CLAUDE.md`, `ROADMAP.md`, `CHANGELOG.md`.
- Dépôt Git (branche `main`), `.gitignore` (exclut `.env`, `*.db`, `backups/`, `__pycache__/`) et `.env.example`.
- `backups/20261114-224413/` : sauvegarde de `main.py`, `database.py` et `revora.db` avant modification.

### Tests effectués
- Rendu des 8 pages via `streamlit.testing` sur une copie de la base : aucune exception.
- Ajout d'interaction, création et validation de relance sur la copie : OK.
- Lancement réel `streamlit run` : Overview et fiche de Thomas Martins affichées sans erreur.
- `revora.db` d'origine non modifiée.

## [0.3.0]
- Prototype initial : navigation, Overview, Prospects, fiche prospect (interactions, timeline, relances).
