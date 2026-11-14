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

## Phase 3 — Activity Manager 🟡
- ✅ Saisie manuelle d'appels, emails et notes
- ✅ Timeline par prospect
- ✅ Relances (création, validation)
- ✅ Compteurs par prospect
- ⬜ Vue Activity globale, prochaines actions du jour

## Phase 4 — Pipeline ⬜
Kanban, étapes personnalisables, filtres, verticales, vue priorisée.

## Phase 5 — Scoring ⬜
Fit, Engagement, Intent, score global, historique et explications, calibration.

## Phase 6 — HubSpot et Gmail ⬜
OAuth, contacts, emails entrants/sortants, activités, webhooks, déduplication, synchronisation contrôlée.

## Phase 7 — Noota ⬜
Vérification des API réellement disponibles, appels, transcriptions, rapprochement contacts, analyse IA.

## Phase 8 — Objection Intelligence ⬜
## Phase 9 — LinkedIn (API officielles uniquement) ⬜
## Phase 10 — AI Copilot ⬜
## Phase 11 — Multi-utilisateur ⬜
## Phase 12 — Production (PostgreSQL, hébergement, sécurité, monitoring) ⬜
