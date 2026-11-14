# CHANGELOG — REVORA

## [0.4.0] — 2026-11-14 — Phase 2 : gestion des prospects

### Ajouté
- Page **Prospects** réorganisée en 3 onglets (l'onglet ouvert est mémorisé) :
  - **Database** : recherche (nom, entreprise, email, poste, téléphone), filtres verticale / statut / source,
    modification d'un prospect, suppression avec case de confirmation et décompte des éléments supprimés.
  - **New prospect** : création avec validation, verticale existante ou nouvelle.
  - **Import CSV** : modèle téléchargeable, séparateurs `,` ou `;`, encodages UTF-8 / Latin-1, en-têtes
    français et HubSpot reconnus, aperçu, rapport (créés / doublons ignorés / lignes rejetées avec raison).
- `database.py` : `update_prospect`, `delete_prospect` (transaction : interactions, relances et scores
  supprimés avec le contact ; l'entreprise est conservée), `count_prospect_activity`, `get_verticals`.
  `create_prospect` accepte en plus `status`, `source`, `owner` (rétrocompatible).
- `core/prospect_service.py` : statuts du pipeline, validation (email, téléphone, statut), détection des
  doublons (même email, ou même prénom + nom + entreprise ; le téléphone seul ne bloque pas), filtres, import CSV.
- 29 nouveaux tests (48 au total).

### Migration de la base
- Nouvelles colonnes, ajoutées automatiquement au lancement sans perte de données :
  `contacts.source`, `contacts.owner`, `contacts.updated_at`, `companies.industry`, `companies.size`, `companies.country`.
- Sauvegarde préalable : `backups/20261114-225551/`.

### Corrigé
- Une entreprise sans verticale était recréée à chaque nouveau contact (`vertical = NULL` ne correspond
  jamais en SQL) : la recherche utilise désormais `IS`.

### Tests effectués
- `python3 -m pytest` : 48 tests réussis ; `revora.db` inchangée (empreinte MD5 identique).
- Interface testée sur une copie de la base : création, doublon refusé, filtre, modification,
  suppression (bouton désactivé tant que la case n'est pas cochée).
- Navigateur, sur une copie du projet : création avec nouvelle verticale « Santé », import d'un CSV
  `;` avec accents (1 créé, 1 doublon, 1 rejeté), onglet conservé après dépôt du fichier.

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
