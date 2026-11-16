# CHANGELOG — REVORA

## [0.38.0] — 2026-11-16 — Phase 13 : fondations de la mémoire (rien ne change à l'écran)

### Ajouté
- **Auteur de chaque action** : colonne `created_by` (identifiant de l'utilisateur actif) sur
  `interactions`, `tasks`, `objections` et `stage_changes`. Elle est remplie par tous les écrans
  (échange, relance, objection, changement d'étape, modification du prospect) avec la personne de la
  vraie connexion ou de « Signed in as ». Elle reste vide si l'équipe est vide, pour les données
  anciennes et pour les synchronisations.
- **`tasks.completed_at`** : date de réalisation d'une relance, fixée au premier « Done » et jamais
  écrasée ensuite.
- **Journal d'événements** (`activity_events`, `core/event_service.py`) : on y ajoute des lignes, sans
  jamais en modifier ni en supprimer. Il note :
  - les suggestions d'objections IA acceptées (catégorie proposée et catégorie retenue) ou refusées ;
  - les brouillons d'email IA gardés ;
  - les relances terminées, avec qui les a faites.
  Un nom d'action inconnu est refusé. Ni email, ni téléphone, ni secret n'y est écrit.
- `activity_service.complete_follow_up` : termine une relance et la note au journal.

### Migration
- Additive : 5 nouvelles colonnes vides, une nouvelle table et un index. Testée sur des copies de
  `revora.db` et `demo.db` : les comptages de lignes sont identiques avant et après.

### Tests
- 408 tests, dont 9 nouveaux dans `tests/test_events.py` :
  - auteur, date de réalisation et journal ;
  - migration d'une ancienne base ;
  - écran réel : clic sur « Done », puis Add et Dismiss avec une IA simulée.
- Toutes les pages s'affichent sans erreur sur la copie de démo migrée.

## [0.37.0] — 2026-11-16 — Phase 12.2 : pilote Render préparé (rien n'est déployé)

### Ajouté
- **`render.yaml`** (Blueprint Render) : service web Python, région Francfort, disque permanent de 1 Go
  (`/opt/render/project/src/storage`), contrôle de santé `/_stcore/health`, déploiement **manuel**
  uniquement ; les valeurs secrètes sont demandées par Render (`sync: false`), jamais dans le dépôt.
- **`deploy/render_start.py`** : crée la base de démo sur le disque si elle manque (jamais d'écrasement),
  garantit `REVORA_ADMIN_EMAIL` comme manager actif, lance Streamlit sur `0.0.0.0:$PORT` avec
  `/etc/secrets/secrets.toml`.
- **Connexion obligatoire en ligne** (`REVORA_REQUIRE_SIGN_IN=1`) : sans configuration complète, l'écran
  « Sign-in is not configured » bloque tout (ni navigation, ni « Signed in as »).
- `user_service.ensure_admin`, `auth_service.sign_in_required`, `seed_demo.py --path FICHIER --if-missing`.
- **`docs/DEPLOY_RENDER.md`** : guide pas à pas (compte, Blueprint, adresse de retour Google, Secret File,
  mises à jour, sauvegardes, arrêt) et points à vérifier au premier déploiement.

### Tests
- 399 tests (7 nouveaux dans `tests/test_deploy.py`). Démarrage simulé « comme sur Render » sur un disque
  temporaire : démo créée (20 prospects), manager ajouté, écran de blocage affiché, santé 200.
- **Non vérifié** (nécessite le compte Render) : construction avec Python 3.15.2, mémoire en 512 Mo,
  acceptation exacte de `render.yaml`.

## [0.36.0] — 2026-11-16 — Phase 12.3 : sauvegardes automatiques et journal des erreurs

### Ajouté
- **Sauvegarde quotidienne automatique** au premier affichage du jour, dans `backups/auto/<base>/`
  (API « backup » de SQLite : copie cohérente même pendant une écriture). Les 14 plus récentes sont
  gardées ; les autres sauvegardes (`backups/<date-heure>/`) et tout fichier étranger ne sont jamais
  supprimés. Une panne de sauvegarde n'empêche jamais l'application de s'ouvrir.
- `backup_db.py` : sauvegarder, lister, **restaurer** (`--restore FICHIER --yes`). La base actuelle est
  d'abord sauvegardée ; une sauvegarde abîmée, un dossier ou un chemin vide sont refusés.
- **Journal des erreurs** `logs/errors.log` (rotation 1 Mo × 3, exclu de Git) : page concernée et détail
  technique de chaque erreur inattendue.
- Settings › **Backups and errors** : dernière sauvegarde, « Back up now », 5 dernières erreurs.
- `core/backup_service.py`, `core/error_log.py`.

### Sécurité (incident pendant les tests, corrigé)
- Un essai de la commande a visé `revora.db` par erreur (variable de test non définie). La restauration
  a échoué avant toute écriture ; `revora.db` a été vérifiée **identique** à la sauvegarde du matin.
  Le test a révélé deux défauts, corrigés : `restore()` acceptait un dossier (chemin vide = « . ») et la
  commande un nom de fichier vide.

### Tests
- 392 tests (8 nouveaux dans `tests/test_backup.py`). Commande testée sur une copie de `demo.db` :
  sauvegarde, liste, refus sans `--yes`, restauration (17 relances retrouvées) avec copie de sécurité.

## [0.35.0] — 2026-11-15 — Phase 12.1 : vraie connexion (voie A)

### Ajouté
- **Vraie connexion** par Google ou Microsoft (`st.login`, norme OIDC) : REVORA ne voit ni ne stocke
  aucun mot de passe. **Inactive tant que `.streamlit/secrets.toml` n'a pas de section `[auth]`
  complète** : sans elle, REVORA reste le prototype local (« Signed in as »), comme avant.
  - Écran « Sign in to REVORA » ; la navigation n'apparaît qu'après connexion.
  - Seuls les **membres actifs de l'équipe** dont l'email correspond peuvent entrer ; email non vérifié
    par le fournisseur refusé ; sinon écran « Access not granted » avec « Sign out ».
  - Barre latérale : « Signed in as **Nom** · Rôle » et « Sign out ».
  - Avec la connexion, **seuls les managers** modifient l'équipe, et un manager ne peut pas se retirer
    ses propres droits (pas de blocage).
- Settings › Team : **email de connexion** de chaque membre (validé, unique sans tenir compte des
  majuscules), état « Sign-in is on / off », alerte si la configuration est incomplète.
  Mise en page revue (email sous le nom ; formulaire d'ajout sur deux lignes) : plus rien de coupé.
- Migration additive : colonne `users.email` + index unique. `core/auth_service.py`,
  `user_service.set_email`, `database.set_user_email`.
- Dépendance **Authlib ≥ 1.3.2** (exigée par `st.login`). Modèle `.streamlit/secrets.toml.example` ;
  procédure dans le README.

### Tests
- 384 tests (9 nouveaux dans `tests/test_auth.py`), sans contacter de vrai fournisseur.
- Navigateur, sur une copie de `demo.db` : sans configuration, rien ne change ; avec une configuration
  factice (hors du projet), l'écran de connexion bloque l'application. Email invalide refusé et effacé.
- **Non vérifié** : une connexion réelle de bout en bout (il faut une application OAuth créée par vous).

## [Documentation] — 2026-11-15 — Conception de REVORA Intelligence

### Ajouté
- `docs/REVORA_INTELLIGENCE.md` : conception de **REVORA Intelligence** (fusion AI Copilot + REVORA
  MEMORY en un seul espace) — compatibilité avec l'existant, données manquantes, architecture cible
  (mémoire relationnelle, provenance, permissions, moteur hors affichage), confidentialité, phasage M1–M5.
- ROADMAP : phase 13 « REVORA Intelligence » (vision, non commencée) et détail de la phase 12.
- Aucun code modifié.

## [0.34.0] — 2026-11-15 — Phase 11.3 : vue équipe dans Performance

### Ajouté
- Performance › **By sales owner** : une ligne par commercial (puis « Unassigned ») avec prospects,
  contactés, appels, taux de connexion, emails, taux de réponse, réunions, conversion, objections.
  - Colonne **Low volume** : les taux calculés sur moins de 10 données, à ne pas comparer.
  - Toujours sur toute l'équipe, quel que soit le filtre « Sales owner ».
  - Affiché aux **managers** (et quand personne n'est choisi dans « Signed in as ») ; un SDR voit
    « The comparison by sales owner is shown to managers ».
- Connecté en **SDR**, le filtre « Sales owner » de Performance part sur ses propres prospects
  (modifiable) ; en manager, sur toute l'équipe. Réinitialisé à chaque changement d'utilisateur.
- `performance_service.by_owner`.

### Tests
- 375 tests (2 nouveaux). Vérifié dans le navigateur sur une copie de `demo.db` : Nina (manager) voit
  Léa, Hugo et Unassigned ; Léa (SDR) voit ses chiffres (9 appels, identiques à sa ligne d'équipe).

## [0.33.0] — 2026-11-15 — Phase 11.2 : « My prospects »

### Ajouté
- Bouton **« My prospects / Everyone »** sur l'Overview, la liste Prospects et le Pipeline, affiché dès
  que quelqu'un est choisi dans « Signed in as ».
  - « My prospects » = prospects dont le Sales owner est l'utilisateur actif.
  - Par défaut : un **SDR** voit ses prospects, un **Manager** voit tout le monde.
  - Le choix est **partagé** entre les trois pages ; il revient au défaut quand on change d'utilisateur.
- Overview en « My prospects » : Today's focus, indicateurs du jour, relances, activité récente et
  « Last 7 days » limités à ses prospects. La recherche couvre toujours toute la base.
  Si aucun prospect ne lui est assigné : état vide avec le bouton « Show everyone ».
- `user_service.default_scope / owned_by / for_prospects`, `shared.scope_prospects`.

### Tests
- 373 tests (4 nouveaux). Vérifié dans le navigateur sur une copie de `demo.db` : Léa (SDR) voit
  6 prospects sur 20 et 2 relances au lieu de 9 ; « Everyone » suit d'une page à l'autre.
  Bouton déplacé sur sa propre ligne (il était coupé dans l'en-tête de l'Overview et du Pipeline).

## [0.32.0] — 2026-11-15 — Phase 11.1 : équipe et utilisateur actif

### Ajouté
- Table **`users`** (nom unique sans tenir compte des majuscules, rôle SDR ou Manager, actif/inactif).
  Migration additive : aucune donnée existante n'est modifiée ; `contacts.owner` reste un nom.
- Settings › **Team** : ajouter un membre, changer son rôle, le désactiver (jamais supprimé : il
  reste dans l'historique). Bouton « Add N sales owner(s) from your prospects » qui reprend les
  propriétaires déjà saisis, sans toucher aux prospects.
- Barre latérale : menu **« Signed in as »**. Le choix est gardé dans l'URL sous forme d'identifiant
  (`?user=3`, jamais le nom) et survit au rechargement. Prototype **sans mot de passe** : une vraie
  connexion viendra avec l'hébergement (phase 12).
- Formulaire prospect : le **Sales owner** se choisit dans l'équipe (« Unassigned » possible) ; pour
  un nouveau prospect, l'utilisateur actif est proposé par défaut. Un propriétaire absent de l'équipe
  est conservé à la modification. Sans équipe, saisie libre comme avant.
- `core/user_service.py`, `database.get_users / add_user / update_user`, `AppContext.users / user`.

### Tests
- 369 tests (5 nouveaux dans `tests/test_users.py`). Vérifié dans le navigateur sur une copie de
  `demo.db` : import de Léa et Hugo, ajout d'une manager, choix gardé après rechargement,
  propriétaire proposé par défaut. `revora.db` et `demo.db` inchangées.

## [0.31.0] — 2026-11-15 — Finitions : étapes dans le fil, infos entreprise

### Ajouté
- Overview › **Recent activity** : les changements d'étape apparaissent dans le fil
  (« Stage → To follow up », icône Kanban, lien vers la fiche), qu'ils viennent du Pipeline, du
  sélecteur d'étape de la fiche ou du formulaire de modification. `database.get_recent_stage_changes`.
- Fiche prospect : panneau **Company** (site, taille, pays) et fenêtre **Edit company**.
  - Les infos sont partagées par tous les contacts de la même entreprise.
  - Site complété automatiquement (`nordvia.com` → `https://nordvia.com`) et vérifié ; taille
    choisie dans une liste (`COMPANY_SIZES`) ; champs vides = effacés.
  - Utilise les colonnes `companies.website/size/country` déjà présentes : aucune migration.
  - `database.update_company_details`, `prospect_service.save_company_details` / `normalize_website`.

### Tests
- 364 tests (6 nouveaux). Vérifié dans le navigateur sur une copie de `demo.db` : infos entreprise
  enregistrées et affichées, changement d'étape visible dans le fil. `revora.db` et `demo.db` inchangées.

## [0.30.0] — 2026-11-15 — Détection des objections par IA

### Ajouté
- Fiche prospect › AI Copilot : bouton **« Find objections in notes »**. L'IA lit les notes des
  10 derniers échanges (sujet et notes uniquement, aucune coordonnée) et **suggère** les objections
  exprimées par le prospect, avec la citation, l'échange d'origine, une catégorie et une explication.
  - Rien n'est enregistré sans clic sur **Add** ; la catégorie peut être corrigée avant ; **Dismiss**
    écarte la suggestion.
  - Garde-fou : une suggestion est écartée si sa citation ne figure pas **mot pour mot** dans les
    notes de l'échange cité, si l'échange n'existe pas, ou si l'objection est déjà enregistrée.
  - L'objection ajoutée est reliée à l'échange, prend sa date et porte la source `ai`, affichée
    « AI (confirmed) » dans le fil de la fiche et le journal des objections.
- `record_objection(..., source=)` (par défaut `manual`) ; `core/copilot_service.py` :
  `OBJECTION_SCHEMA`, `build_objection_context`, `build_objection_prompt`, `validate_objections`.

### Corrigé
- Le panneau AI Copilot de la fiche restait parfois replié après un clic (clé stable + état mémorisé).

### Tests
- 358 tests (8 nouveaux dans `tests/test_objection_detection.py`). Vérifié en réel avec Gemini sur une
  copie de la démo : 4 objections justes trouvées dans 2 échanges, aucune inventée, une déjà saisie
  correctement écartée. `revora.db` inchangée.

## [0.29.0] — 2026-11-15 — Base de démonstration fictive

### Ajouté
- `python3 seed_demo.py` crée **`demo.db`**, une base SÉPARÉE et entièrement fictive :
  20 prospects (5 verticales, 2 commerciaux), environ 90 échanges sur 45 jours (appels avec durée,
  emails, LinkedIn, notes en français), objections (ouvertes, traitées, perdues), relances dont
  certaines en retard, qualification, deux réponses de playbook. Emails en `.example`, numéros
  factices. Contenu déterministe ; dates calculées à partir d'aujourd'hui.
  - refuse d'écrire dans `revora.db` ; refuse d'écraser `demo.db` sans `--reset`
    (qui ne supprime que `demo.db`).
- Variable `REVORA_DATABASE` : `REVORA_DATABASE=demo.db streamlit run main.py` lance l'application
  sur une autre base. Sans elle, toujours `revora.db`.
- Bandeau **« Demo database: demo.db »** dans la barre latérale dès que la base n'est pas `revora.db`.
- `database.set_created_at` : antidate une fiche ou une relance — réservé aux bases autres que
  `revora.db` et aux tables `contacts` / `tasks` (pour des dates de démo cohérentes).

### Tests
- 350 tests (9 nouveaux : base séparée, données fictives et passées, déterminisme, protection de
  `revora.db`, `--reset`, choix de base, rendu des 8 pages sur la démo, cohérence des dates,
  garde-fous de l'antidatage). Vérifié dans le navigateur sur `demo.db`. `revora.db` inchangée.

## [0.28.0] — 2026-11-15 — Style des brouillons d'email

### Ajouté
- Settings › AI features › **Email drafts** : langue (Auto / English / French), ton
  (Formal / Friendly) et signature. « Formal » impose le vouvoiement en français ; « Friendly »
  garde le vouvoiement sauf si l'historique montre déjà un tutoiement. La signature remplace
  « [Your name] ». Réglage `ai_email_style` (valeurs inconnues → valeurs par défaut).

### Modifié
- Brouillons d'email : 2 à 4 courts paragraphes, salutation et formule de politesse sur leurs
  propres lignes, consigne de relecture orthographique.
- Consigne générale : REVORA est l'outil interne du SDR, jamais présenté au prospect comme le
  produit vendu (défaut observé lors d'un essai réel, puis vérifié corrigé).

### Vérifié en réel (Gemini, données de démo, lecture seule)
- Français / Formal avec signature : vouvoiement, 3 paragraphes, signature appliquée, sans coquille.
- English / Friendly sans signature : « [Your name] » conservé.
- Après correction : « REVORA » n'apparaît plus dans les brouillons.

### Tests
- 341 tests (5 nouveaux : style par défaut, consignes, style limité aux emails, style transmis
  depuis la fiche, enregistrement depuis Settings).

## [0.27.0] — 2026-11-15 — Phase 10.2 : chat AI Copilot sur toute la base

### Ajouté
- Page **AI Copilot** : chat (« Who should I follow up with this week? »…) répondant uniquement à
  partir des données REVORA :
  - réponse courte, puis **Sources** dépliables (faits et hypothèses, chacun avec ses
    enregistrements : « Call · 15/11 · Thomas Martins ») ;
  - boutons **Open <prospect>** pour ouvrir la fiche des prospects cités ;
  - question hors sujet → réponse polie (« Je ne peux vous aider que sur les données REVORA ») ;
  - **lecture seule** : le chat ne modifie rien ; historique gardé dans la session du navigateur ;
  - questions d'exemple, bouton « New chat », consommation affichée.
- `core/copilot_service.py` : instantané de la base (jusqu'à 200 prospects, prioritaires d'abord ;
  étape, score, dernier échange avec **extrait de notes de 200 caractères**, prochaine relance,
  objections ouvertes, totaux), consignes du chat, schéma de réponse, vérification des sources.
  Jamais envoyé : email, téléphone, URL LinkedIn. Les 6 derniers messages du chat sont renvoyés.

### Vérifié en réel (Gemini, données de démo, lecture seule)
- Question métier : 1,9 s, 608 / 245 jetons, faits sourcés, hypothèse séparée, aucun élément écarté.
- Question hors sujet : refusée poliment, en français.
- Consigne ajoutée après l'essai : ne pas écrire d'identifiants (P1, I1…) dans la réponse — vérifié.

### Tests
- 336 tests (8 nouveaux : instantané, extrait, limite et priorités, historique, validation,
  interface du chat avec faux fournisseur, ouverture d'une fiche, erreur affichée).

## [0.26.1] — 2026-11-15 — Gemini : plus d'attente sans fin, premier essai réel réussi

### Corrigé
- La génération pouvait « tourner » plusieurs minutes : `gemini-3.8-flash` répondait **503**
  (« high demand ») puis **504**, et le kit Google relançait longtemps en silence.
  Désormais : délai maximum de 45 s par modèle, aucune relance automatique du kit, et repli
  immédiat sur l'autre modèle en cas de surcharge (500, 502, 503, 504). Délai dépassé ou réseau
  coupé → message clair au lieu d'une attente.

### Modifié
- Modèle principal Gemini : **`gemini-3.5-flash-lite`** (rapide, disponible, gratuit) ;
  `gemini-3.8-flash` devient le modèle de repli.

### Vérifié en réel (clé de l'utilisateur, données de démo Thomas Martins, lecture seule)
- « Prepare my call » : 1,4 s, 469 / 243 jetons, 2 faits tous sourcés, 1 hypothèse,
  4 questions, aucun élément écarté.
- « Draft a follow-up email » : 2,0 s, 472 / 175 jetons, sources réelles, aucun élément écarté.
  Défauts observés : une coquille (« je me perm »), tutoiement choisi par le modèle — relecture
  par le commercial indispensable (le brouillon n'est jamais envoyé automatiquement).

### Tests
- 328 tests (3 nouveaux : repli en cas de surcharge, surcharge partout, délai dépassé).

## [0.26.0] — 2026-11-15 — AI Copilot : Google Gemini en fournisseur alternatif

### Ajouté
- Settings › AI features › **AI provider** : Anthropic Claude (`claude-opus-5-5`) ou
  **Google Gemini** (`gemini-3.8-flash`, offre gratuite). Avertissement affiché pour Gemini :
  « Google may use the content sent to improve its products » — données de démo uniquement.
- `ai/gemini_client.py` : même interface que le client Claude ; appel
  `client.models.generate_content` avec `system_instruction`, `response_mime_type="application/json"`
  et `response_json_schema` ; refus, coupure et erreurs (clé rejetée, quota gratuit atteint)
  traduits en messages clairs. Clé lue dans `.env` (`GEMINI_API_KEY`).
- `ai/providers.py` : choix du fournisseur (réglage `ai_provider`, Claude par défaut).
- Fiche prospect : le panneau indique le fournisseur utilisé ; « free tier » au lieu d'un coût pour Gemini.
- Dépendance `google-genai>=3.3.0` ; `.env.example` mis à jour.

### Vérifications de la documentation
- Page tarifs officielle (15/11/2026) : `gemini-3.8-flash` est gratuit sur l'offre gratuite ;
  contenu « utilisé pour améliorer nos produits » sur l'offre gratuite, pas sur l'offre payante.
- La documentation récente présente une nouvelle « Interactions API », sans paramètre de consigne
  système documenté : REVORA utilise `generate_content`, dont les paramètres ont été vérifiés dans
  le kit installé (google-genai 3.3.0).

### Tests
- 325 tests (8 nouveaux, faux client Gemini). Vérifié dans le navigateur sur une copie de la base,
  sans clé. **Non vérifié** : un appel réel à Gemini (aucune clé configurée).

## [0.25.0] — 2026-11-15 — Phase 10.1 : AI Copilot dans la fiche prospect

### Ajouté
- Fiche prospect › panneau **AI Copilot** (désactivé par défaut) :
  - **Prepare my call** : faits (chacun avec sa source : « Call · 10/11 · Discovery »), hypothèses à
    vérifier, questions à poser, prochaine étape à proposer ;
  - **Draft a follow-up email** : brouillon à relire et copier — REVORA ne l'envoie jamais ;
    bouton « Save draft as a note » (enregistrement seulement sur clic).
  - Consommation et coût estimé affichés sous chaque résultat.
- Settings › **AI features** : ce qui est envoyé, état de la clé, interrupteur « Enable AI features »
  (grisé sans clé).
- `core/copilot_service.py` : contexte envoyé (10 derniers échanges, objections, réponses du
  playbook concernées, **jamais** email / téléphone / LinkedIn), consignes, schémas de réponse,
  vérification des sources (un fait sans source réelle est écarté et signalé).
- `ai/claude_client.py` : appel à Claude Opus 5.5 (`claude-opus-5-5`) avec réponse au format imposé
  (structured outputs), effort « low », repli automatique en cas de refus (`fallbacks: "default"`),
  erreurs traduites en messages clairs. Clé lue dans `.env` (`ANTHROPIC_API_KEY`).
- Dépendance `anthropic>=2.8.0` ; `.env.example` mis à jour.

### Modifié
- Page AI Copilot : renvoie vers le panneau de la fiche ; le chat global est prévu en 10.2.

### Tests
- 317 tests (14 nouveaux) avec un **faux client** : aucun appel réel, aucun coût. Vérifié dans le
  navigateur sur une copie de la base, sans clé : panneau désactivé, interrupteur grisé.
- **Non vérifié** : un appel réel à l'API (aucune clé configurée). À faire avec votre clé.

## [0.24.0] — 2026-11-15 — Palette et langue harmonisées

### Décisions
- **Palette de référence : le brand kit**, avec un seul emprunt au cahier des charges : le gris
  secondaire lisible **#9295A1** (contraste 6,6 sur le fond, contre 4,1 pour l'ancien #6B7280,
  sous le minimum recommandé de 4,5 pour du petit texte).
- **Interface entièrement en anglais.** Le code et ses commentaires restent en français.

### Modifié
- `ui/theme.py`, `ui/kanban.py`, `.streamlit/config.toml` : texte secondaire en #9295A1 via le jeton
  `COLORS["gray"]` (les gris #9CA3AF écrits en dur ont disparu).
- Environ 70 messages traduits (confirmations, erreurs de saisie, doublons, import CSV, étapes,
  scoring) : « Interaction enregistrée » → « Interaction saved », « Prospect deplace vers… » →
  « Prospect moved to… », etc.
- **Étapes par défaut des nouvelles bases** en anglais (To prospect, First attempt, In contact,
  Interested, Meeting scheduled, To follow up, Not interested, Disqualified).
  **Votre base garde ses étapes actuelles** (données non modifiées) : renommez-les dans
  Pipeline › Stages si vous le souhaitez.
- Un prospect créé sans étape va dans la **première étape réelle** du pipeline (et non plus dans
  « A prospecter » écrit en dur, qui aurait créé une étape fantôme dans une base renommée).
- Les en-têtes CSV en français (prénom, société, téléphone…) restent reconnus à l'import.

### Tests
- 303 tests (1 nouveau ; attentes de messages et d'étapes mises à jour). Les 9 pages rendues sans
  erreur sur une **copie** de la base réelle, étapes françaises intactes. `revora.db` non modifiée.

## [0.23.0] — 2026-11-15 — Corriger les saisies

### Ajouté
- **Modifier ou supprimer une interaction** depuis la timeline de la fiche prospect (icône ✏️) :
  formulaire pré-rempli, mêmes règles de validation qu'à la saisie, score recalculé.
  Suppression protégée par une case « I understand this cannot be undone ».
  - Seules les saisies **manuelles** sont modifiables : une interaction HubSpot ou Gmail appartient
    à sa source (elle serait recréée à la synchronisation suivante) — pas d'icône ✏️, refus côté service.
  - Les objections notées pendant l'échange supprimé sont **conservées** (elles ont été réellement
    exprimées) ; elles perdent seulement leur lien vers l'échange.
- `database` : `get_interaction`, `update_interaction`, `delete_interaction` (transaction) ;
  `activity_service` : `edit_interaction`, `remove_interaction`, `is_editable`.

### Corrigé
- Le formulaire d'interaction (page Activity et fiche prospect) **garde la saisie en cas d'erreur** ;
  il n'est vidé qu'après un enregistrement réussi (`clear_on_submit=False` + `reset_form`).
- Objections › Log : le message de confirmation s'affiche enfin après une correction
  (enregistrement dans un callback du tableau, sans relance supplémentaire qui l'effaçait).

### Modifié
- `activity_service._validate` : règles de validation partagées par la saisie et la correction.

### Tests
- 302 tests (6 nouveaux). Vérifié dans le navigateur sur une **copie** de la base : correction d'un
  appel (score 0 → 9), suppression (objection conservée, score revenu à 0), message du journal des
  objections. `revora.db` n'a pas été modifiée.

## [0.22.0] — 2026-11-15 — P2.4 : Pipeline, définitions et confirmation des étapes fermées

### Ajouté
- **Définition des étapes** (Pipeline › Stages) : un champ « Definition » par étape (« quand un
  prospect entre-t-il dans cette étape ? »), rédigé par l'équipe — REVORA n'en invente aucune.
  Elle s'affiche au survol de l'en-tête de colonne du tableau, dans l'aide du sélecteur d'étape
  de la fiche prospect et dans le bandeau de confirmation.
- **Confirmation avant une étape fermée** : glisser une carte vers « Non intéressé », « Disqualifié »
  (ou toute étape marquée Closed), ou la choisir dans la fiche prospect, affiche un bandeau
  « Move … to the closed stage …? » avec **Confirm move** / **Cancel**. Rien n'est enregistré avant
  la confirmation ; en cas d'annulation, la carte revient à sa place. Les étapes ouvertes restent
  immédiates.
- `database.set_stage_definition` ; `get_stages` renvoie `definition`.
- `screens/shared.py` : `request_stage_change`, `stage_change_confirmation`.

### Base de données
- Migration additive : colonne `pipeline_stages.definition` (vide par défaut, aucune donnée modifiée).

### Limite connue
- Le formulaire **Edit** (fiche et page Prospects) change l'étape sans cette confirmation :
  c'est une action explicite en deux temps (saisie puis Save).

### Tests
- 296 tests (4 nouveaux). Vérifié dans le navigateur sur une **copie** de la base : glisser-déposer
  vers une étape ouverte (immédiat), vers une étape fermée (bandeau, annulation → carte revenue,
  confirmation → enregistré), définition au survol. `revora.db` n'a pas été modifiée.

## [0.21.0] — 2026-11-15 — P2.3 : Performance, faible volume et filtre par commercial

### Ajouté
- **Alerte « faible volume »** : un taux calculé sur moins de 10 données (appels, prospects contactés
  ou invités) garde sa valeur mais porte une icône orange ⚠ sur sa carte, une explication au survol,
  et une ligne récapitulative orange (« connection rate: 2 calls, reply rate: 2 prospects contacted… »).
  Seuil : `performance_service.MIN_SAMPLE`.
- **Filtre « Sales owner »** : limite tous les indicateurs (cartes, graphique, tableau par verticale)
  aux prospects des commerciaux choisis, « Unassigned » compris. Il porte sur le commercial du
  **prospect** : REVORA n'enregistre pas encore qui a saisi chaque interaction (phase 11) — c'est
  indiqué dans l'aide et dans « How are these indicators calculated? ».
- `compute_kpis` renvoie aussi `invited` (prospects invités sur LinkedIn), base du taux d'acceptation.
- `performance_service` : `MIN_SAMPLE`, `low_volume_rates`, `owner_options`, `filter_by_owner`.

### Tests
- 292 tests (6 nouveaux). Vérifié dans le navigateur sur une **copie** de la base : icônes, ligne
  d'alerte, filtre sur un commercial (2 appels → 1). `revora.db` n'a pas été modifiée.

## [0.20.0] — 2026-11-15 — P2.2 : Activity, source et état des synchronisations

### Ajouté
- Activity › Timeline : filtre **« Source »** (Manual, HubSpot, Gmail, et toute autre source présente)
  et colonne **« Source »** dans le tableau.
- Ligne **« Sync: »** au-dessus des filtres : état de chaque connecteur tel qu'il est enregistré
  (« not connected » en gris, « last sync 15/11 13:04 » en vert, « error: … » en rouge), avec un
  raccourci vers Settings. Rien n'est supposé : sans synchronisation enregistrée, c'est « not connected ».
- `activity_service` : `SOURCE_LABELS`, `source_label`, `source_options`, `filter_by_source`, `sync_status`.

### Modifié
- `timeline_service` réutilise `SOURCE_LABELS` d'`activity_service` (une seule définition).

### Tests
- 286 tests (5 nouveaux). Vérifié dans le navigateur sur une **copie** de la base (un appel manuel,
  un email Gmail fictif, une erreur Gmail simulée) : filtre, couleurs d'état et raccourci Settings.
  `revora.db` n'a pas été modifiée.

## [0.19.0] — 2026-11-15 — P2.1 : Objections reliées à leur échange

### Ajouté
- Fiche prospect › **Record an objection** : champ facultatif **« Raised during »** pour relier
  l'objection à l'un des 10 derniers échanges du prospect. L'objection prend alors la date de cet
  échange (et non l'heure de saisie), ce qui rend les statistiques par semaine exactes.
- Objections › **Log** : colonne **« Raised during »** (ex. « Call · 15/11 13:04 · Discovery ») et
  **catégorie corrigeable** directement dans le tableau, comme le statut.
- Timeline de la fiche : l'objection indique « during Call » quand elle est reliée.
- `database.set_objection_category`, `objection_service.change_category`, `interaction_label`,
  `source_interaction` ; `get_objections` renvoie aussi le canal, le sujet et la date de l'échange d'origine.

### Corrigé
- Objections : après une modification dans le journal, la page revenait sur l'onglet Insights ;
  elle reste désormais sur **Log** (`on_change="rerun"` sur les onglets).

### Sécurité des données
- Un échange d'un **autre** prospect est refusé (« Cet échange n'appartient pas à ce prospect. »).

### Tests
- 281 tests (6 nouveaux). Vérifié dans le navigateur sur une **copie** de la base : appel saisi,
  objection reliée, catégorie corrigée puis rétablie. `revora.db` n'a pas été modifiée.

## 2026-11-15 — Dépôt GitHub

### Ajouté
- Dépôt distant `origin` : https://github.com/enzomangiaracina-design/revora (public, choix validé).
- Fusion du commit initial créé par GitHub : notre README est conservé ; le `.gitignore` réunit
  nos règles et le modèle Python de GitHub (aucun fichier suivi n'est exclu par la fusion).
- Vérifié avant envoi : ni `.env`, ni `revora.db`, ni `backups/`, ni document externe dans l'historique.

## [0.18.0] — 2026-11-15 — P1 : Cockpit SDR (Today's Focus enrichi)

### Ajouté
- Chaque ligne du **Today's Focus** affiche :
  - le **type d'action** (Follow up, Call, Email, LinkedIn, Prepare), déduit des données : relance due,
    sinon canal du dernier échange, sinon téléphone puis email disponibles (« Prepare » s'il n'y a ni l'un ni l'autre) ;
  - l'**échéance** (« Overdue 2 d » en rouge, « Today » en orange, « Due 30/11 ») et le dernier contact ;
  - une **raison vérifiable avec source et date** : « Follow-up due 13/11 (scheduled 10/11) »,
    « Never contacted · added 01/11 via Import CSV », « No touch for 25 d · last call on 21/10 ».
- **Actions rapides** : ouvrir la fiche, **terminer** la relance due, **reporter** la relance (+1 j, +3 j,
  +1 semaine), **« Not now »** : écarter un prospect du focus jusqu'à une date, avec raison facultative
  (correction d'une priorité proposée). Les prospects écartés reviennent automatiquement à la date prévue ;
  « Show them again » les remet tout de suite.
- Base : table `focus_snoozes` ; `reschedule_task`, `snooze_prospect`, `unsnooze_prospect`,
  `get_active_snoozes` ; le résumé d'activité donne aussi l'id et la date de création de la prochaine
  relance et le canal du dernier échange. Suppression d'un prospect : sa mise à l'écart part avec lui.
- 21 nouveaux tests (275 au total), dont 5 tests d'interface qui cliquent sur les actions rapides.

### Non fait (volontairement)
- « Préparer un brouillon » (blueprint) : nécessite l'IA (phase 10 / P3).

### Tests effectués
- `python3 -m pytest` : 275 tests réussis ; `revora.db` inchangée.
- Navigateur sur une copie (4 prospects fictifs : relance en retard, relance du jour, jamais contacté,
  inactif) : lignes, couleurs d'échéance, menu « Plus tard » ; boutons empilés → colonne élargie.
- Sauvegarde préalable : `backups/20261115-083847/`. Migration : table `focus_snoozes`.

## [0.17.0] — 2026-11-15 — P0.4 : états vides et erreurs communs

### Ajouté
- **`empty_state`** (`screens/shared.py`) : un seul modèle d'état vide pour toute l'application — icône,
  titre, explication et **actions pour continuer** (ajouter un prospect, importer un CSV, saisir une activité,
  ouvrir le pipeline). Les boutons prennent la largeur de leur texte et passent à la ligne si besoin.
- **`no_results`** : état des listes filtrées sans résultat (« No … matches these filters »).
- **`error_state`** + garde dans `main.py` : une erreur inattendue dans une page affiche un message clair
  (« Your data is safe »), les actions *Try again* / *Back to Overview* et les détails techniques repliés,
  au lieu d'une trace Python brute. Le menu reste utilisable. Les mécanismes internes de Streamlit
  (`st.rerun`…) ne sont pas interceptés (ce sont des `BaseException`).
- 17 états vides harmonisés sur Overview, Prospects, Pipeline (dont tableau vide), Activity, Objections,
  AI Copilot, Performance et la fiche prospect.
- `tests/test_ui_states.py` : 18 tests d'interface (toutes les pages sur base vide, états vides et leurs
  actions, erreur interceptée, `st.rerun` non intercepté). 254 tests au total.

### Tests effectués
- `python3 -m pytest` : 254 tests réussis ; `revora.db` inchangée (les tests d'interface utilisent une base
  temporaire).
- Navigateur sur une base vide : états vides de l'Overview ; boutons tronqués dans les colonnes étroites
  → rangée horizontale à largeur naturelle ; écran d'erreur vérifié en provoquant volontairement une
  erreur dans une copie de test.
- Sauvegarde préalable : `backups/20261115-083336/`. Aucune migration de base.

## [0.16.0] — 2026-11-15 — P0.3 : fiche prospect 360°

### Ajouté
- **En-tête** : identité, poste, entreprise, verticale ; propriétaire, score, source, lien LinkedIn ;
  **étape modifiable directement** ; actions principales **Log interaction**, **Follow-up**, **Objection**,
  **Edit** (fenêtres qui réutilisent les formulaires existants).
- **Prochaine action toujours visible** (en retard / aujourd'hui), avec bouton « Done ».
- **Timeline unifiée** (`core/timeline_service.py`) : interactions, relances, objections, changements
  d'étape, variations de score et création de la fiche, filtrable par type ; source affichée
  (HubSpot, Gmail) quand l'événement ne vient pas d'une saisie manuelle.
- **Historique des changements d'étape** : table `stage_changes` (ancienne étape, nouvelle étape, origine :
  pipeline, formulaire, suppression d'étape), enregistré automatiquement ; supprimé avec le prospect.
- **Panneaux de contexte repliables** : coordonnées, activité, score (explication et historique),
  qualification, préparation d'appel, objections, relances.
- 8 nouveaux tests (236 au total).

### Modifié
- La fiche passe de 11 sections empilées à une mise en page en deux colonnes ; les formulaires
  permanents (interaction, relance, objection) sont remplacés par des fenêtres.
- `get_prospect_by_id` et `get_tasks` renvoient aussi la date de création en heure locale.

### Tests effectués
- `python3 -m pytest` : 236 tests réussis ; `revora.db` inchangée.
- Inventaire sur une copie : toutes les fonctions de l'ancienne fiche présentes ; changement d'étape
  (historique + timeline), qualification, statut d'objection, relance terminée, ouverture des 4 fenêtres.
- Navigateur : compteurs tronqués dans la colonne étroite → remplacés par une ligne compacte.
- Sauvegarde préalable : `backups/20261115-082841/`. Migration : table `stage_changes`.

## [0.15.0] — 2026-11-15 — P0.2 : navigation du blueprint

### Modifié
- **Menu dans l'ordre du blueprint** : Overview, Prospects, Pipeline, Activity, Objections, AI Copilot,
  Performance, Settings (« Prospecting Pipeline » affiché « Pipeline »).
- **La fiche prospect n'est plus une entrée de menu** : elle s'ouvre par-dessus la page en cours, avec un
  bouton « Back to <page> ». Choisir une page dans le menu ferme la fiche.
- Ouverture de la fiche depuis : Overview (focus, recherche, activité récente), Pipeline (cartes),
  **Prospects (clic sur une ligne du tableau, bouton « Open file »)**.
- Une session restée sur l'ancienne entrée « Prospect Details » est convertie sans erreur.

### Détail technique
- `open_prospect` / `close_prospect` / `go_to` dans `screens/shared.py` ; état `prospect_open`.
- Tableau cliquable : la sélection est remise à zéro après ouverture (clé de tableau versionnée),
  sinon la fiche se rouvrirait au retour.

### Tests effectués
- `python3 -m pytest` : 228 tests réussis ; `revora.db` inchangée. Les 8 pages du menu s'affichent sans erreur.
- Parcours (sur une copie) : Overview → fiche → retour ; fiche ouverte puis menu → fiche fermée ;
  Prospects « Open file » ; ancienne session « Prospect Details ».
- Navigateur : clic sur une ligne du tableau → fiche, retour sans réouverture ; carte du Pipeline →
  fiche avec « Back to Pipeline ».
- Sauvegarde préalable : `backups/20261115-082426/`. Aucune migration de base.

## [0.14.1] — 2026-11-15 — P0.1 : découpage de l'interface en pages

Première étape de P0 (blueprint Produit & UX). **Aucun changement de comportement.**

### Modifié
- `main.py` (2 251 lignes) découpé : il ne garde que la configuration, les données communes, la navigation
  et l'appel de la page (90 lignes).
- `screens/` : un module par page avec `render(ctx)` ; `shared.py` (formulaires, cartes, navigation entre
  pages, fenêtre d'ajout) ; `common.py` (imports communs) ; `AppContext` (prospects, étapes, scores).
- Le découpage a été fait par un **script** qui recopie chaque bloc de page sans le modifier. Seule
  adaptation : le formulaire prospect lit la liste des étapes via `get_stage_names()` au lieu d'une
  variable globale (même valeur).

### Vérifications
- **Relevé de toutes les pages** (356 éléments affichés, dans l'ordre) sur une base fictive identique :
  relevé stable (deux passes identiques), puis **identique avant et après** le découpage.
- Interactions entre modules : ouverture d'une fiche depuis l'Overview, création d'un prospect,
  saisie d'une interaction, relance terminée — toutes fonctionnelles.
- `python3 -m pytest` : 228 tests réussis ; navigateur : Overview et Pipeline (Kanban) affichés.
- Sauvegarde préalable : `backups/20261115-081759/`. Aucune migration de base.

## [0.14.0] — 2026-11-15 — Phase 9 : LinkedIn (saisie manuelle, conforme)

REVORA **ne se connecte pas à LinkedIn** : aucune API ouverte ne donne accès aux relations, messages ou
profils d'autres membres, l'API Sales Navigator est fermée aux nouveaux partenaires, et les conditions
d'utilisation interdisent scraping et automatisation. Détails et sources : `docs/LINKEDIN.md`.

### Ajouté
- **URL du profil LinkedIn** sur les prospects : formulaire, import CSV (colonnes « linkedin »,
  « profil linkedin »…), fiche prospect (lien « Open profile »), liste des prospects.
  Mise en forme unique (`https://www.linkedin.com/in/<identifiant>`), validation (seuls les profils
  `/in/` sont acceptés), **détection de doublon par profil LinkedIn**.
- **Actions LinkedIn** dans le formulaire d'interaction : *Connection request sent*, *Connection accepted*,
  *InMail sent* — réservées au type LinkedIn, sens fixé automatiquement, objet facultatif.
- **Scoring** : invitation acceptée = 10 points d'Engagement (plafond 10), distincte d'une réponse (15).
- **Performance** : invitations envoyées, taux d'acceptation, messages LinkedIn envoyés.
  Une invitation acceptée n'est pas comptée comme une réponse.
- Base : colonne `contacts.linkedin_url` (migration automatique). `update_prospect` conserve l'URL
  existante si l'argument n'est pas fourni.
- `docs/LINKEDIN.md`. 19 nouveaux tests (228 au total).

### Sécurité
- L'identifiant du profil est limité aux caractères utilisés par LinkedIn : une URL piégée ne peut pas
  détourner le lien affiché (testé).

### Tests effectués
- `python3 -m pytest` : 228 tests réussis ; `revora.db` inchangée. Les 9 pages s'affichent sans erreur.
- Sur une copie : URL ajoutée par le formulaire (normalisée), URL invalide refusée, lien dans la fiche,
  action LinkedIn enregistrée comme sortante, indicateurs LinkedIn dans Performance ; vérification visuelle.
- Sauvegarde préalable : `backups/20261115-080507/`. Migration : colonne `contacts.linkedin_url`.

## [0.13.1] — 2026-11-15 — Correctifs du formulaire prospect

### Corrigé
- **Ordre de la touche Tab** : les champs étaient posés dans une seule paire de colonnes, Tab
  parcourait donc toute la colonne de gauche (Prénom → Entreprise → Poste…). Une paire de colonnes
  par ligne : Tab suit maintenant l'ordre de lecture (Prénom → Nom → Entreprise → Verticale…).
- **Saisie perdue en cas d'erreur** : le formulaire de création se vidait même quand la validation
  échouait. Il garde désormais la saisie, et n'est vidé qu'après une création réussie
  (`reset_form` : nouveau numéro de version du formulaire).
- Concerne les trois usages du formulaire : Prospects › New prospect, Prospects › modification,
  fenêtre « Add prospect » de l'Overview.

### Tests effectués
- `python3 -m pytest` : 209 tests réussis ; `revora.db` inchangée.
- Sur une copie : erreur de validation → saisie conservée ; création → formulaire vidé ;
  modification toujours pré-remplie et enregistrée ; ordre de Tab vérifié dans le navigateur.
- Sauvegarde préalable : `backups/20261115-080000/`.

### Remarque
- Le formulaire d'interaction (`interaction_form`) se vide aussi en cas d'erreur : non modifié ici.

## [0.13.0] — 2026-11-15 — Overview : cockpit du SDR

Refonte de la page Overview selon la direction « minimaliste fonctionnelle » : elle répond à
« Où en suis-je ? », « Quels prospects demandent mon attention ? », « Que faire ensuite ? ».
Aucune donnée inventée : chaque section réutilise des requêtes existantes.

### Ajouté
- **En-tête** : salutation selon l'heure, date du jour, recherche de prospects (`filter_prospects`),
  bouton **Add prospect** (fenêtre réutilisant le formulaire et les contrôles existants).
- **4 KPI** : appels du jour et emails envoyés du jour (écart avec la veille), relances dues
  (dont en retard, en rouge), prospects prioritaires.
- **Today's focus** : 8 prospects classés par `prioritize()` — priorité (High / Medium / Low selon les
  points d'urgence), entreprise, étape, score, dernier contact, **action recommandée déduite de la
  raison** (relance à faire, premier contact, relance après inactivité ; aucune IA), raison, bouton
  d'ouverture de la fiche ; lien vers toutes les priorités du pipeline.
- **Recent activity** : fil chronologique des interactions, objections, nouveaux prospects et variations
  de score (≥ 5 points), chaque événement ouvre la fiche du prospect.
- **Last 7 days** : taux de connexion, taux de réponse, rendez-vous (écart avec les 7 jours précédents)
  et tendance sur 14 jours ; lien vers la page Performance.
- États vides utiles : base vide (ajout, import CSV), rien d'urgent (lien pipeline), aucune activité
  (lien vers la saisie d'activité).
- `core/overview_service.py` (mise en forme pure), `database.get_recent_score_changes` (lecture, LAG SQL).
- Thème : titres de section compacts ; sur petit écran, cartes KPI en grille de 2 colonnes.
- 20 nouveaux tests (209 au total).

### Modifié
- Les onglets des pages Prospects et Activity peuvent être ouverts depuis une autre page
  (`on_change="rerun"`), nécessaire pour les liens des états vides.
- Retirés de l'Overview : le tableau complet des prospects (toujours sur la page Prospects) et les
  compteurs cumulés ; les anciens compteurs faisaient une requête par prospect.

### Problèmes trouvés et corrigés pendant les vérifications
- Boutons « Open » tronqués → bouton icône ; libellé « Follow-ups due · x overdue » coupé → écart rouge.
- Mini-cartes « Last 7 days » tronquées dans la colonne étroite → liste compacte.
- Grille mobile : l'espacement de 16 px faisait passer la 2e carte à la ligne → largeur corrigée.
- Le lien « Import a CSV file » ouvrait le mauvais onglet → onglets pilotables (voir ci-dessus).

### Défauts préexistants repérés (non corrigés, hors périmètre)
- Formulaire prospect : la touche Tab parcourt la colonne de gauche avant celle de droite.
- Formulaire prospect : les champs se vident quand la validation échoue.

### Tests effectués
- `python3 -m pytest` : 209 tests réussis ; `revora.db` inchangée. Les 9 pages s'affichent sans erreur.
- Navigateur sur une copie avec données fictives : KPI, focus et raisons, ouverture de fiche,
  fenêtre d'ajout (erreur de validation puis création), recherche, fil d'activité, résumé 7 jours,
  affichage mobile (375 px) ; sur une base vide : états vides et leurs liens.
- Sauvegarde préalable : `backups/20261115-001608/`. Aucune migration de base.

## [0.12.0] — 2026-11-15 — Page Performance (module H)

### Ajouté
- Page **Performance** : période 7 / 30 / 90 jours, comparaison avec la période précédente
  (écart en valeur ou en points), cartes KPI simples conformes à la charte.
  - **Activité** : appels effectués, appels par jour ouvré, taux de connexion, emails envoyés,
    emails par jour ouvré.
  - **Résultats** : taux de réponse, rendez-vous obtenus, taux de conversion, objections,
    délai moyen entre deux relances.
  - Activité quotidienne (appels, emails envoyés, réponses), tableau **par verticale**.
  - Définitions de chaque indicateur affichées dans la page.
- `core/performance_service.py` : calculs purs et documentés. Un taux sans dénominateur affiche
  « — » plutôt qu'un 0 % trompeur. Jours ouvrés = lundi à vendredi.
- 10 nouveaux tests (189 au total), valeurs vérifiées à la main.

### Non disponible
- Performance par séquence : REVORA n'a pas encore de séquences (prévu avec la connexion HubSpot).
- Vues manager et équipe : prévues avec la gestion des utilisateurs (phase 11).

### Tests effectués
- `python3 -m pytest` : 189 tests réussis ; `revora.db` inchangée.
- Les 9 pages s'affichent sans erreur (sur une copie).
- Navigateur sur une copie avec un mois d'activité fictive : indicateurs, écarts colorés dans le bon
  sens (un délai de relance qui augmente est en rouge), graphique quotidien, tableau par verticale.
- Sauvegarde préalable : `backups/20261115-000621/`. Aucune migration de base.

## [0.11.0] — 2026-11-15 — Phase 8 : Objection Intelligence (saisie manuelle)

Règle appliquée : **aucune objection n'est inventée**. Seules les objections saisies par le
commercial sont enregistrées et comptées. La détection par IA viendra plus tard (à confirmer).

### Ajouté
- Base : tables `objections` (catégorie, formulation, **étape du pipeline au moment de l'objection**,
  statut Open / Handled / Lost, source, interaction liée) et `objection_responses` (réponses
  recommandées par catégorie). Fonctions d'ajout, lecture, statut, suppression.
- Saisie :
  - formulaire d'interaction : champs facultatifs « Objection raised » et « Objection wording »,
    l'objection est reliée à l'interaction ;
  - fiche prospect : section **Objections** (statut modifiable, suppression d'une erreur, ajout direct).
- Fiche prospect : **« Prepare the next call »** — objections déjà exprimées (ouvertes d'abord),
  formulations du prospect et réponse du playbook ; dépliée automatiquement s'il reste une objection ouverte.
- Page **Objections** :
  - filtres période et verticale ; indicateurs : total, ouvertes, taux de traitement, plus fréquente ;
  - **Insights** : objections les plus fréquentes, évolution par semaine, répartition par verticale,
    par étape du pipeline et par entreprise, taux de traitement par catégorie ;
  - **Playbook** : réponse recommandée par catégorie (rédigée par le commercial, modèle en 4 temps
    proposé) et **exemples de formulations anonymisés** (nom, entreprise, emails, téléphones, liens retirés) ;
  - **Log** : toutes les objections, statut modifiable directement dans le tableau.
- `core/objection_service.py` : catégories (10 par défaut + nouvelles), statistiques, anonymisation,
  préparation d'appel.
- 21 nouveaux tests (179 au total).

### Modifié
- `add_interaction` retourne l'identifiant de l'interaction créée (toujours « vrai » comme avant).
- Supprimer un prospect supprime aussi ses objections (dans la même transaction).

### Problèmes trouvés pendant les tests
- Paramètres `interaction_id` et `occurred_at` rendus **nommés obligatoirement** : passés par
  position, une date pouvait être prise pour un identifiant (erreur de clé étrangère).
- Graphique « Most frequent objections » trié par ordre alphabétique → trié par fréquence.

### Tests effectués
- `python3 -m pytest` : 179 tests réussis ; `revora.db` inchangée.
- Les 9 pages s'affichent sans erreur (sur une copie).
- Navigateur sur une copie avec objections fictives : indicateurs, graphiques, playbook (exemples
  anonymisés), préparation d'appel dans la fiche prospect.
- Sauvegarde préalable : `backups/20261114-235755/`. Migration : tables `objections`, `objection_responses`.

## [0.10.0] — 2026-11-14 — Pipeline façon HubSpot (glisser-déposer)

Mise en page inspirée du pipeline HubSpot, aux couleurs de la charte REVORA.
La capture HubSpot fournie n'a servi que de modèle visuel : aucune de ses données n'a été reprise.

### Ajouté
- `ui/kanban.py` : tableau Kanban en **composant personnalisé Streamlit** (API components v2,
  incluse dans Streamlit 1.67, aucune dépendance ajoutée) :
  - colonnes de largeur fixe avec défilement horizontal, « nom de l'étape + compteur » ;
  - **glisser-déposer** d'une carte vers une autre colonne → étape enregistrée en base, compteurs
    mis à jour, message de confirmation ;
  - cartes : entreprise en titre (lien), Created / Last activity / Next follow-up / Owner / Score,
    séparateur, contact avec avatar à initiales, icônes « ouvrir la fiche » et « relances » ;
  - relance en retard en rouge, inactivité en orange, colonne vide « No prospect » ;
  - toutes les données insérées avec `textContent` (aucune exécution de contenu).
- En-tête du pipeline : vues **Board / Table / Priorities / Stages**, recherche, bouton **Filter**
  (verticale, température, score minimum, seuil d'inactivité, étapes fermées), **Sort by**.
- Filtres rapides sous la barre, comme HubSpot : **Sales owner**, **Create date**, **Last activity**,
  **Next follow-up** (le libellé affiche le filtre actif).
- Clic sur une carte → ouverture directe de la fiche du prospect.
- `core/pipeline_service.py` : `build_card`, `sort_prospects` (5 tris), `filter_quick`,
  `format_date`, `initials`. `get_all_prospects` renvoie aussi `created_at_local`.
- 18 nouveaux tests (158 au total).

### Modifié
- Les anciennes cartes Streamlit (menu déroulant pour changer d'étape) sont remplacées par le composant.
- Onglets du pipeline remplacés par un sélecteur de vue (comme la bascule tableau / kanban de HubSpot).

### Tests effectués
- `python3 -m pytest` : 158 tests réussis ; `revora.db` inchangée.
- Les 9 pages s'affichent sans erreur (sur une copie).
- Navigateur (1440 px) sur une copie avec 8 prospects fictifs : tableau, glisser-déposer (étape
  enregistrée en base, compteurs, message), clic → fiche prospect, filtre rapide, vue Table.
  Le glisser-déposer a été déclenché par des événements HTML5 natifs : l'automatisation à la souris
  du navigateur de test ne les produit pas. **À confirmer à la main** sur votre Mac.
- Sauvegarde préalable : `backups/20261114-234921/`. Aucune migration de base.

### Différences avec HubSpot
- Pas d'onglet « Mes transactions » : REVORA n'a pas encore d'utilisateurs (phase 11).
- Pas de montant ni de date de fermeture : REVORA suit des prospects, pas des transactions.

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
