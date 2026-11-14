# CHANGELOG — REVORA

## [0.3.2] — 2026-11-14

### Ajouté
- Structure du projet, sans déplacer aucun fichier existant (`main.py` importe toujours `database.py` directement) :
  - `core/scoring.py` : calcul du score global (0,35 / 0,40 / 0,25), pondérations configurables et validées.
  - `core/deduplication.py` : `normalize_email`, `normalize_phone` (format E.164, numéros français).
  - `core/prospect_service.py`, `core/activity_service.py` : emplacements réservés (phases 2 et 3).
  - `integrations/base.py` : interface `BaseConnector` (authenticate, test_connection, fetch_events,
    normalize_event, sync_events) et `NormalizedEvent`.
  - `integrations/hubspot|gmail|noota|linkedin/` : dossiers réservés, aucune API appelée ni supposée.
  - `ai/copilot.py`, `ai/call_analysis.py`, `ai/objection_detection.py` : emplacements réservés.
- `requirements.txt`, `pytest.ini`.
- `tests/` : 19 tests (persistance SQLite sur base temporaire, imports de `main.py`, doublons, normalisation, scoring).
- `.gitignore` : ajout de `.pytest_cache/`.

### Tests effectués
- `python3 -m pytest` : 19 tests réussis.
- Empreinte MD5 de `revora.db` identique avant/après les tests.
- Rendu des 8 pages via `streamlit.testing` sur une copie de la base : aucune exception.
- Sauvegarde préalable : `backups/20261114-225040/`.

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
