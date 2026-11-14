# CHANGELOG — REVORA

## [0.9.0] — 2026-11-14 — Branding (avant la phase 8)

Application de l'identité visuelle du brand kit (`REVORA_Brand_Kit/REVORA_Direction_Artistique.pdf`).
Phases 6 (HubSpot / Gmail, partie en ligne) et 7 (Noota) mises en pause à la demande.

### Ajouté
- `.streamlit/config.toml` : thème centralisé — palette officielle (Lavande #A78BFA, Violet #7C3AED,
  Nuit #0B0B12, Ardoise #1A1A24, Gris #6B7280, Blanc cassé #F8FAFC), police **Inter**
  (Regular / Medium / SemiBold), rayons 8 px, couleurs des graphiques, barre latérale.
- `ui/theme.py` : jetons de design (couleurs, grille 4 px, rayons 8 / 12 px), logo, signature,
  styles des cartes KPI (Ardoise, rayon 12 px, valeur en blanc) et navigation latérale
  (élément actif en violet, sans rond de sélection), icônes de navigation.
- `assets/brand/` : logo horizontal, logo avec descripteur, monogramme, favicon — découpés des PNG
  du brand kit, fond rendu transparent.
- Logo dans la barre latérale (monogramme quand elle est repliée), descripteur
  « Sales Execution Platform », favicon, titre d'onglet, signature sur l'Overview.

### Modifié
- `main.py` : l'ancien bloc CSS (couleurs approximatives) est remplacé par `theme.apply_theme()`.
  La valeur des KPI passe de lavande à blanc : le violet est réservé aux actions et à la sélection.

### Écarts assumés par rapport à la charte
- **Logo raster provisoire** : le brand kit précise que le monogramme définitif doit être redessiné
  en SVG. Les PNG d'`assets/brand/` sont à remplacer par ces exports.
- **Icônes** : la charte prévoit Lucide ; Streamlit n'intègre que Material Symbols. Une seule
  famille est utilisée (Material, style linéaire) pour ne pas mélanger les styles.
- **Police** chargée depuis Google Fonts par le navigateur (pas de fichier embarqué).

### Tests effectués
- `python3 -m pytest` : 140 tests réussis ; `revora.db` inchangée.
- Les 9 pages s'affichent sans erreur (sur une copie de la base).
- Navigateur (1440 px) : Overview, Pipeline, fiche prospect, Activity ; navigation active,
  barre latérale repliée (monogramme).
- Sauvegarde préalable : `backups/20261114-234054/`. Aucune migration de base.

## [0.8.0] — 2026-11-14 — Phase 6 (partie hors ligne) : connecteurs HubSpot et Gmail

**Aucun compte externe n'est connecté.** Connecteurs écrits d'après la documentation officielle
(vérifiée le 14/11/2026) et testés uniquement avec des données fictives. Voir `docs/INTEGRATIONS.md`.

### Ajouté
- `integrations/http.py` : client HTTP sans dépendance (urllib), retries sur 429 / 5xx,
  respect de `Retry-After`, transport remplaçable dans les tests.
- `integrations/config.py` : lecture des secrets depuis `.env` sans écraser les variables du terminal.
- `integrations/hubspot/connector.py` : recherche paginée et incrémentale (hs_lastmodifieddate) des
  appels et emails, contacts associés, normalisation (sens, durée en ms, résultats d'appel par GUID
  documentés), import des contacts. Contenu des emails / notes d'appel non importé par défaut.
- `integrations/gmail/connector.py` : scope minimal `gmail.metadata` (en-têtes uniquement),
  synchronisation complète puis partielle par l'historique, retour à la complète si l'historique a
  expiré (404), brouillons / spam / corbeille ignorés, sens déterminé par l'expéditeur.
- `core/sync_service.py` : rattachement aux contacts (identifiant CRM, puis téléphone unique, puis
  email ; une clé ambiguë passe à la suivante), déduplication (identifiant externe ; même email vu par
  Gmail et HubSpot), journal, mémoire de la dernière synchronisation, import des contacts HubSpot
  (un contact sans entreprise est rejeté plutôt que complété par supposition).
- Base : table `integration_syncs` ; `add_external_interaction` (INSERT OR IGNORE, idempotent),
  `set_hubspot_id`, état des intégrations ; `create_prospect` accepte `hubspot_id`.
- Settings → **Integrations** : état, jeton détecté ou non, dernière synchronisation, boutons
  « Sync now » / « Import contacts » désactivés tant qu'aucun jeton n'est configuré, journal.
- `.env.example` : variables HubSpot et Gmail commentées. `docs/INTEGRATIONS.md`.
- 27 nouveaux tests (140 au total).

### Constats importants de la documentation
- Gmail : toutes les autorisations de lecture sont **restreintes** (vérification Google, audit de
  sécurité si stockage serveur) ; `q` interdit avec `gmail.metadata`.
- HubSpot : aucune propriété `Message-ID` documentée pour les emails → rapprochement Gmail/HubSpot
  par contact + sens + objet + fenêtre de 3 minutes.

### Tests effectués
- `python3 -m pytest` : 140 tests réussis, aucun appel réseau ; `revora.db` inchangée.
- Interface sur une copie : toutes les pages ; Settings → Integrations, boutons désactivés sans jeton.
- Sauvegarde préalable : `backups/20261114-232841/`. Migration : table `integration_syncs`.

### À confirmer sur des comptes de test
- Réponse de la lecture groupée des associations HubSpot ; version d'API (v3 ou datée).
- Unité d'`internalDate` Gmail et forme des enregistrements d'historique.

## [0.7.0] — 2026-11-14 — Phase 5 : Scoring

### Ajouté
- **Moteur de scoring** (`core/scoring.py`, sans accès à la base) :
  - **Fit** : verticales cibles (50) et mots-clés de poste (50), selon le profil cible configuré.
    Sans profil configuré, le Fit est « non évalué » et le score global est calculé sur les
    dimensions disponibles (aucune valeur inventée).
  - **Engagement** : réactions observées du prospect (réponse email, appel entrant, réponse LinkedIn,
    conversation, réponse positive), avec plafonds par type et décroissance temporelle (demi-vie 30 j).
    Les tentatives sans réaction ne rapportent **aucun** point.
  - **Intent** : qualification confirmée par le commercial (besoin, décideur, budget, démo) et réunion
    obtenue (observée). Étape fermée : 0.
  - Score global pondéré 35 / 40 / 25, seuils Hot ≥ 70, Warm ≥ 40.
  - Chaque point est expliqué et typé : observé / confirmé / règle.
- `core/score_service.py` : configuration, recalcul, historique, aide à la calibration.
- **Fiche prospect** : score global, Fit / Engagement / Intent, température, « Why this score? »,
  historique des variations (graphique et tableau), formulaire **Qualification**.
- **Pipeline** : score sur chaque carte, filtres score minimum et température ; priorités départagées par le score.
- **Prospects** : colonnes Score et Temperature. **Overview** : indicateur « Hot prospects ».
- Nouvelle page **Settings** : profil cible, pondérations, seuils, demi-vie, retour aux valeurs par défaut,
  tableau de calibration (score moyen par étape), rappel des règles de points.
- Base : table `settings` ; colonnes `contacts.need_identified`, `is_decision_maker`, `budget_confirmed`,
  `demo_requested` ; colonne `scores.explanation`. L'historique n'enregistre une ligne que si un score change.
- 19 nouveaux tests (113 au total).

### Tests effectués
- `python3 -m pytest` : 113 tests réussis ; `revora.db` inchangée.
- Interface sur une copie : toutes les pages ; qualification → Intent 55, global 21 (sans Fit) ;
  profil cible enregistré → Fit 100, global 49 ; pondérations invalides refusées ; filtre de score.
- Navigateur sur une copie : fiche prospect (56 · Warm), explication détaillée des points.
- Sauvegarde préalable : `backups/20261114-232034/`.

### Limites connues
- Points, plafonds, pondérations et seuils sont **provisoires** : ils devront être calibrés sur de vraies conversions.
- Pas encore de signaux « inférés par l'IA » (phases 7, 8 et 10) ni de visites de site.

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
