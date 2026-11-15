# REVORA

> *Your prospecting, intelligently orchestrated.*

REVORA est un espace de travail de prospection pour SDR/BDR : il mémorise les
interactions (appels, emails, notes), organise le portefeuille de prospects et
aide à décider quelle action effectuer ensuite.

Statut : **prototype local** (Streamlit + SQLite), version 0.18.0.

## Lancer l'application

Depuis le dossier du projet :

```bash
cd ~/Documents/REVORA
```

```bash
streamlit run main.py
```

L'application s'ouvre sur http://localhost:8501. Pour l'arrêter : `Ctrl + C` dans le terminal.

Pour (re)créer les tables sans lancer l'interface :

```bash
python3 database.py
```

## Prérequis

- Python 3 (testé avec 3.15.2)
- Dépendances listées dans `requirements.txt` :

```bash
python3 -m pip install -r requirements.txt
```

## Lancer les tests

```bash
python3 -m pytest
```

Les tests utilisent une base temporaire : ils ne touchent jamais `revora.db`.

## Structure

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée : configuration, données communes, navigation, appel de la page choisie |
| `screens/` | Une page par module (`overview.py`, `prospects.py`, `prospect_details.py`, `pipeline.py`, `activity.py`, `objections.py`, `copilot.py`, `performance.py`, `settings.py`) ; `shared.py` : formulaires et composants communs ; `common.py` : imports communs |
| `database.py` | Accès à la base SQLite : création des tables et toutes les fonctions de lecture/écriture |
| `revora.db` | Base SQLite locale. **Ne jamais la supprimer.** |
| `backups/` | Copies horodatées des fichiers et de la base, faites avant chaque modification importante |
| `requirements.txt` | Liste des bibliothèques Python nécessaires |
| `pytest.ini` | Configuration des tests |
| `core/` | Logique métier : `prospect_service.py` (validation, doublons, filtres, import CSV), `scoring.py` (moteur de scoring Fit / Engagement / Intent), `score_service.py` (configuration, historique, calibration), `deduplication.py` (normalisation email/téléphone), `activity_service.py` (interactions, relances, périodes), `pipeline_service.py` (Kanban, inactivité, priorités), `objection_service.py` (objections, statistiques, anonymisation), `performance_service.py` (indicateurs de performance), `overview_service.py` (cockpit de l'Overview), `timeline_service.py` (timeline de la fiche prospect), `sync_service.py` (synchronisation, rattachement, déduplication) |
| `integrations/` | `base.py` (interface commune), `http.py` (client HTTP avec retries), `config.py` (secrets .env), connecteurs `hubspot/` et `gmail/` (hors ligne, voir `docs/INTEGRATIONS.md`) ; `noota/` réservé, `linkedin/` : pas de connecteur par choix (voir `docs/LINKEDIN.md`) |
| `ui/` | Interface : `theme.py` (jetons de design, logo, styles), `kanban.py` (tableau du pipeline avec glisser-déposer) |
| `.streamlit/config.toml` | Thème : palette, police Inter, rayons (source unique des couleurs) |
| `assets/brand/` | Logo, monogramme, favicon (raster provisoires issus du brand kit) |
| `docs/` | Documentation technique (`INTEGRATIONS.md` : HubSpot et Gmail ; `LINKEDIN.md` : API LinkedIn et choix de la saisie manuelle) |
| `ai/` | Copilot, analyse d'appels, détection d'objections (réservés, aucun modèle connecté) |
| `tests/` | Tests automatiques pytest |
| `CLAUDE.md` | Règles du projet pour l'assistant IA |
| `ROADMAP.md` | Phases de développement |
| `CHANGELOG.md` | Historique des modifications |
| `.gitignore` | Fichiers que Git ignore (`.env`, base, sauvegardes, caches) |
| `.env.example` | Modèle des variables secrètes, à copier en `.env` |

## Git

Le projet est versionné avec Git (branche `main`). `revora.db` et `backups/` ne sont
**pas** versionnés : ils contiennent des données de prospects et restent uniquement sur ce Mac.

```bash
git status
```

```bash
git add -A && git commit -m "Description de la modification"
```

## Modules

| Module | État |
|---|---|
| Overview | Cockpit du SDR : KPI du jour, Today's focus (type d'action, échéance, raison sourcée, actions rapides), activité récente, résumé 7 jours |
| Prospects | Fonctionnel : recherche, filtres, création, modification, suppression confirmée, import CSV |
| Prospect Details | Fonctionnel : coordonnées, compteurs, dernière interaction, prochaine action, saisie d'interactions, timeline, relances |
| Activity | Fonctionnel : indicateurs du jour, timeline globale filtrable, relances par échéance, saisie rapide |
| Prospecting Pipeline | Fonctionnel : tableau façon HubSpot (glisser-déposer), filtres rapides, tri, vues Table / Priorités / Étapes |
| Settings | Fonctionnel : configuration du scoring, calibration, état des intégrations (non connectées) |
| Objections | Fonctionnel : saisie, statistiques, playbook de réponses, exemples anonymisés, journal |
| Performance | Fonctionnel : indicateurs d'activité et de résultats, comparaison de périodes, par verticale |
| AI Copilot | Page vide (à venir) |

## Base de données

Tables : `companies`, `contacts`, `interactions`, `scores`, `tasks`, `integrations`.
Le chemin de la base est calculé à partir de l'emplacement de `database.py`,
donc l'app utilise toujours `~/Documents/REVORA/revora.db`, quel que soit le dossier d'où on la lance.

## Sauvegarder la base

```bash
sqlite3 revora.db ".backup backups/revora-$(date +%Y%m%d-%H%M%S).db"
```
