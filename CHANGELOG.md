# CHANGELOG — REVORA

## [0.6.0] — 2026-11-14 — Phase 4 : Pipeline

### Ajouté
- Page **Prospecting Pipeline** (onglets mémorisés), avec des filtres communs : recherche, verticale,
  commercial, seuil d'inactivité (14 jours par défaut), « seulement inactifs », « afficher les étapes fermées ».
  - **Board** (Kanban) : une colonne par étape. Chaque carte affiche l'entreprise, la verticale et la prochaine
    relance (en rouge si elle est en retard), signale les prospects inactifs ou jamais contactés, et propose
    un menu pour changer d'étape (déplacement immédiat).
  - **Priorities** : vue priorisée par règles simples et explicables (relance en retard +3, relance du jour +2,
    jamais contacté +1, inactif +1 ; étapes fermées exclues), avec la raison affichée pour chaque prospect.
    Règles provisoires en attendant le scoring (phase 5).
  - **Stages** : renommer (les prospects suivent), réordonner, marquer une étape comme fermée, ajouter,
    supprimer (avec choix de l'étape où déplacer ses prospects ; au moins une étape conservée).
- Table `pipeline_stages` (nom, position, fermée) : créée automatiquement avec les 8 étapes par défaut ;
  tout statut déjà utilisé par un prospect est ajouté pour qu'aucun prospect ne soit perdu.
- Les statuts du formulaire prospect et des filtres viennent désormais des étapes du pipeline ;
  sans statut, un nouveau prospect entre dans la première étape.
- Filtre **Sales owner** (commercial) dans la page Prospects.
- `core/pipeline_service.py` : tableau, calcul d'inactivité, priorités.
- 21 nouveaux tests (94 au total).

### Corrigé
- Les comparaisons de noms ignorant la casse ne géraient pas les lettres accentuées (`lower()` de SQLite) :
  « SOCIÉTÉ GÉNÉRALE » et « Société Générale » créaient deux entreprises. Comparaison faite en Python (`casefold`).

### Tests effectués
- `python3 -m pytest` : 94 tests réussis ; `revora.db` inchangée.
- Interface sur une copie : toutes les pages, déplacement d'une carte, priorités, renommage / ajout /
  réordonnancement / suppression d'étapes, statuts dynamiques dans les filtres.
- Navigateur (1440 px) sur une copie : tableau, relance en retard en rouge, inactivité, priorités,
  déplacement d'une carte vers « Rendez-vous obtenu ».
- Sauvegarde préalable : `backups/20261114-231303/`. Migration : création de la table `pipeline_stages`.

### Limites connues
- Pas de glisser-déposer : Streamlit ne le propose pas nativement (il faudrait un composant tiers).
- Le filtre par score attendra le moteur de scoring (phase 5).

## [0.5.0] — 2026-11-14 — Phase 3 : Activity Manager

### Ajouté
- Page **Activity** (onglets mémorisés) :
  - indicateurs : appels et emails du jour, interactions sur 7 jours, relances du jour et en retard ;
  - **Timeline** globale : filtres période / type / prospect ou entreprise, durée des appels, prochaine étape ;
  - **Follow-ups** : relances classées En retard / Aujourd'hui / À venir / Sans date, bouton « Done », historique des terminées ;
  - **Log activity** : saisie rapide d'une interaction pour n'importe quel prospect.
- Formulaire d'interaction commun (page Activity et fiche prospect) : canal LinkedIn, date et heure réelles
  de l'interaction, durée d'appel, prochaine étape et **création automatique d'une relance** si une date est choisie.
- Fiche prospect : compteurs appels / emails / LinkedIn / notes, dernière interaction, prochaine action,
  relances en retard signalées, relances terminées repliées.
- Liste des prospects : colonnes Calls, Emails, Last activity, Next follow-up (calculées automatiquement).
- `database.py` : `get_all_interactions` (filtres canal et dates), `get_all_tasks`, `get_activity_summary` ;
  `add_interaction` accepte `occurred_at` et `metadata` (rétrocompatible).
- `core/activity_service.py` : validation (pas d'interaction dans le futur, relance après l'interaction),
  regroupement des relances, périodes, compteurs, format des durées.
- 25 nouveaux tests (73 au total).

### Corrigé
- Les heures étaient affichées en **UTC** (1 h de moins qu'à Paris en hiver). Elles restent stockées en UTC
  dans la base et sont désormais converties en heure locale à l'affichage et pour les filtres par date.
- Les messages de confirmation de la fiche prospect disparaissaient immédiatement (effacés par `st.rerun()`).

### Tests effectués
- `python3 -m pytest` : 73 tests réussis ; `revora.db` inchangée.
- Interface sur une copie de la base : saisie avec relance, compteurs, timeline (heure locale, durée),
  refus d'une saisie vide, relance terminée depuis la page Activity, toutes les pages sans erreur.
- Navigateur sur une copie : page Activity (indicateurs, timeline, relances en retard / à venir).
- Sauvegarde préalable : `backups/20261114-230744/`. Aucune migration de structure dans cette version.

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
