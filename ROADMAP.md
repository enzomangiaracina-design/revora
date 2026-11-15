# ROADMAP — REVORA

Légende : ✅ fait · 🟡 en cours · ⬜ à faire

## Phase 1 — Stabilisation ✅
- ✅ Audit du projet
- ✅ Correction de l'erreur d'import `get_prospect_by_id`
- ✅ Vérification SQLite (intégrité OK, données de démonstration présentes)
- ✅ Stabilisation du lancement (toutes les pages s'affichent sans erreur)
- ✅ Tests automatisés de persistance (pytest, 19 tests)
- ✅ Git initialisé (`.gitignore`, `.env.example`)
- ✅ Structure `core/`, `integrations/`, `ai/`, `tests/`, `requirements.txt`

## Phase 2 — Prospect Management ✅
- ✅ Création avec validation et détection des doublons
- ✅ Modification des fiches
- ✅ Suppression avec confirmation
- ✅ Import CSV (rapport détaillé)
- ✅ Recherche et filtres (verticale, statut, source)
- ✅ Verticales personnalisables (choisir ou saisir)
- ✅ Édition des infos entreprise : site, taille, pays (v0.31.0)
- ⬜ Plus tard : filtre par commercial (phase 4),
  synchronisation CRM (phase 6)

## Phase 3 — Activity Manager ✅
- ✅ Saisie manuelle d'appels, emails, LinkedIn et notes (date/heure réelles, durée d'appel)
- ✅ Timeline par prospect et timeline globale filtrable
- ✅ Relances : création (aussi depuis une interaction), classement par échéance, validation
- ✅ Compteurs automatiques (fiche prospect, liste, indicateurs du jour)
- ✅ Heures affichées en heure locale
- ✅ Modifier / supprimer une interaction saisie à la main (v0.23.0)
- ⬜ Plus tard : synchronisation automatique (phases 6-7)

## Phase 4 — Pipeline ✅
- ✅ Kanban avec changement d'étape depuis la carte
- ✅ Étapes personnalisables (renommer, réordonner, ajouter, supprimer, fermer)
- ✅ Filtres : recherche, verticale, commercial, inactivité ; étapes fermées masquables
- ✅ Prospects sans activité récente (seuil réglable)
- ✅ Vue priorisée (règles provisoires, raisons affichées)
- ✅ Tableau façon HubSpot : glisser-déposer, cartes détaillées, filtres rapides, tri, vue table (v0.10.0)
- ⬜ Plus tard : « Mes prospects » (après la gestion des utilisateurs, phase 11)

## Phase 5 — Scoring ✅
- ✅ Fit Score (profil cible configurable)
- ✅ Engagement Score (réactions observées, plafonds, décroissance temporelle)
- ✅ Intent Score (qualification confirmée, réunion obtenue, étape fermée = 0)
- ✅ Score global pondéré, seuils Hot / Warm / Cold configurables
- ✅ Historique des variations et explication de chaque point
- ✅ Aide à la calibration (score moyen par étape)
- ⬜ Plus tard : calibration sur de vraies conversions, signaux IA, synchronisation des scores vers HubSpot (phase 6)

## Branding ✅ (inséré avant la phase 8)
- ✅ Thème centralisé : palette officielle, police Inter, rayons, cartes KPI, navigation
- ✅ Logo, monogramme, favicon (raster provisoires issus du brand kit)
- ⬜ Logo vectoriel SVG définitif (à fournir), icônes Lucide (nécessite une interface hors Streamlit)

## Décisions de design ✅ (v0.24.0)
- ✅ Palette : brand kit + gris secondaire lisible #9295A1
- ✅ Langue de l'interface : anglais

## Phase 6 — HubSpot et Gmail ⏸ (en pause)
- ✅ Vérification des API dans la documentation officielle (`docs/INTEGRATIONS.md`)
- ✅ Connecteurs HubSpot (appels, emails, contacts) et Gmail (en-têtes) — hors ligne, testés avec données fictives
- ✅ Rattachement aux contacts, déduplication (y compris Gmail ↔ HubSpot), journal, synchronisation incrémentale
- ⬜ Comptes de **test** créés par l'utilisateur, puis validation sur de vraies réponses d'API
- ⬜ Flux OAuth complet (obtention et renouvellement des jetons)
- ⬜ Webhooks HubSpot (serveur FastAPI)
- ⬜ Écriture contrôlée des scores vers HubSpot (après validation)

## Phase 7 — Noota ⏸ (en pause)
Vérification des API réellement disponibles, appels, transcriptions, rapprochement contacts, analyse IA.

## Phase 8 — Objection Intelligence ✅
- ✅ Saisie manuelle (interaction, fiche prospect), catégories personnalisables, statuts
- ✅ Statistiques : fréquence, évolution, par verticale, entreprise et étape du pipeline
- ✅ Playbook de réponses recommandées, exemples anonymisés
- ✅ Préparation d'appel dans la fiche prospect
- ✅ Détection et catégorisation par IA dans les notes, citations vérifiées, toujours à confirmer (v0.30.0)
- ⬜ Plus tard : détection dans les transcriptions d'appels (après Noota, phase 7)
## P0 — Fondations UX (blueprint Produit & UX) ✅
- ✅ P0.1 Découpage de l'interface : une page = un module (`screens/`), sans changement de comportement
- ✅ P0.2 Navigation : ordre du blueprint, fiche prospect ouverte depuis les listes (v0.15.0)
- ✅ P0.3 Fiche prospect 360° : en-tête, timeline unifiée, historique des changements d'étape (v0.16.0)
- ✅ P0.4 États vides / erreur communs à toutes les pages (v0.17.0)

## P1 — Cockpit SDR (blueprint) ✅
- ✅ Today's Focus : type d'action, échéance, raison avec source et date (v0.18.0)
- ✅ Actions rapides : ouvrir, terminer, reporter, « Not now » (mise à l'écart datée)
- ✅ Brouillons d'emails / préparation assistée par l'IA (phase 10.1, v0.25.0)

## P2 — Finitions (blueprint) ✅
- ✅ P2.1 Objections : échange d'origine (« Raised during »), catégorie corrigeable dans le journal (v0.19.0)
- ✅ P2.2 Activity : filtre et colonne « Source », ligne d'état des synchronisations (v0.20.0)
- ✅ P2.3 Performance : alerte « faible volume » (< 10 données), filtre par commercial du prospect (v0.21.0)
- ✅ P2.4 Pipeline : définition des étapes, confirmation avant une étape fermée (v0.22.0)

## Overview — cockpit du SDR ✅
- ✅ KPI du jour, Today's focus explicable, fil d'activité, résumé 7 jours, états vides, mobile
- ✅ Changements d'étape affichés dans le fil « Recent activity » (v0.31.0)

## Module H — Performance ✅ (avant la phase 9)
- ✅ Indicateurs individuels, comparaison de périodes, activité quotidienne, par verticale
- ✅ Vues manager / équipe (v0.34.0)
- ⬜ Par séquence (avec HubSpot)

## Phase 9 — LinkedIn ✅ (saisie manuelle, conforme)
- ✅ Vérification des API officielles et des conditions d'utilisation (`docs/LINKEDIN.md`)
- ✅ URL du profil (formulaire, import CSV, fiche, doublons)
- ✅ Actions LinkedIn (invitation, acceptation, InMail), scoring et performance
- ⬜ Pas de connecteur : aucune API ouverte ne le permet (à revoir si une intégration Sales Navigator officielle devient disponible)
## Phase 10 — AI Copilot ✅
- ✅ 10.1 Fiche prospect : préparation d'appel (faits sourcés, hypothèses, questions) et brouillon d'email,
  sur clic, désactivé par défaut, sans coordonnées envoyées, sources vérifiées (v0.25.0)
- ✅ Fournisseur au choix : Claude ou Google Gemini (offre gratuite, données de démo uniquement) (v0.26.0)
- ✅ Premier appel réel (Gemini, données de démo) : brief et email corrects et sourcés, ~2 s (v0.26.1)
- ⬜ Premier appel réel avec Claude (nécessite une clé Anthropic)
- ✅ 10.2 Chat sur l'ensemble de la base : réponses sourcées, lecture seule, hors-sujet refusé (v0.27.0)
- ✅ Style des brouillons d'email : langue, ton (vouvoiement), signature (v0.28.0)
## Base de démonstration ✅ (v0.29.0)
- ✅ `seed_demo.py` : 20 prospects fictifs et leur historique dans `demo.db`, base séparée
- ✅ `REVORA_DATABASE=demo.db` pour lancer l'application dessus, bandeau « Demo database »

## Phase 11 — Multi-utilisateur ✅ (prototype, sans mot de passe)
- ✅ 11.1 Équipe (rôles SDR / Manager, actif / inactif), menu « Signed in as », propriétaire choisi
  dans l'équipe (v0.32.0) — sans mot de passe pour l'instant
- ✅ 11.2 « My prospects » : Overview, liste et pipeline limités à l'utilisateur actif (v0.33.0)
- ✅ 11.3 Vue équipe « By sales owner » (managers) et performance personnelle par défaut (SDR) (v0.34.0)
- ⬜ Vraie connexion (identifiants) : avec l'hébergement, phase 12
## Phase 12 — Production (PostgreSQL, hébergement, sécurité, monitoring) ⬜
- ✅ Voie choisie : **A**, pilote SQLite sur disque permanent ; PostgreSQL plus tard (mémoire M3/M4)
- ✅ 12.1 Vraie connexion (st.login, OIDC Google / Microsoft), inactive sans configuration (v0.35.0)
- ⬜ 12.1 bis Premier test réel avec une application OAuth de test (à créer par l'utilisateur)
- ⬜ 12.2 Hébergement du pilote (choix de l'hébergeur, disque permanent, HTTPS), données de démo uniquement
- ⬜ 12.3 Sauvegardes automatiques et suivi des erreurs
- ⬜ Organisations (isolation des données entre entreprises)

## Phase 13 — REVORA Intelligence (AI Copilot + REVORA MEMORY) ⬜ vision, non commencée
Conception : `docs/REVORA_INTELLIGENCE.md`. Un seul espace (Copilot · Memory & Knowledge ·
Personalization), un seul assistant. Ne démarre qu'après les fondations (phase 12.1, identité, ergonomie).
- ⬜ I0 Regroupement : « AI Copilot » devient « REVORA Intelligence » (3 onglets)
- ⬜ Fondations mémoire : auteur des actions (`created_by`), journal d'événements, `tasks.completed_at`
- ⬜ M1 Interaction Memory : recherche plein texte, souvenirs prospect sourcés et validés
- ⬜ M2 User Memory : observation → hypothèse → préférence confirmée (nécessite la vraie connexion)
- ⬜ M3 Knowledge Memory : objection → réponse utilisée → issue, par secteur
- ⬜ M4 Personalized Copilot : souvenirs autorisés cités comme sources (PostgreSQL + pgvector conseillés)
- ⬜ M5 Team Memory : pratiques validées par les managers, isolation par organisation
