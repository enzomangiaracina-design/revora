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
- ⬜ Plus tard : édition des infos entreprise (site, taille, pays), filtre par commercial (phase 4),
  synchronisation CRM (phase 6)

## Phase 3 — Activity Manager ✅
- ✅ Saisie manuelle d'appels, emails, LinkedIn et notes (date/heure réelles, durée d'appel)
- ✅ Timeline par prospect et timeline globale filtrable
- ✅ Relances : création (aussi depuis une interaction), classement par échéance, validation
- ✅ Compteurs automatiques (fiche prospect, liste, indicateurs du jour)
- ✅ Heures affichées en heure locale
- ⬜ Plus tard : modifier / supprimer une interaction saisie par erreur, synchronisation automatique (phases 6-7)

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

## Phase 8 — Objection Intelligence 🟡
- ✅ Saisie manuelle (interaction, fiche prospect), catégories personnalisables, statuts
- ✅ Statistiques : fréquence, évolution, par verticale, entreprise et étape du pipeline
- ✅ Playbook de réponses recommandées, exemples anonymisés
- ✅ Préparation d'appel dans la fiche prospect
- ⬜ Détection et catégorisation automatiques par IA (après Noota / AI Copilot), toujours à confirmer
## Phase 9 — LinkedIn (API officielles uniquement) ⬜
## Phase 10 — AI Copilot ⬜
## Phase 11 — Multi-utilisateur ⬜
## Phase 12 — Production (PostgreSQL, hébergement, sécurité, monitoring) ⬜
