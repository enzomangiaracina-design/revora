# REVORA

> *Your prospecting, intelligently orchestrated.*

REVORA est un espace de travail de prospection pour SDR/BDR : il mémorise les
interactions (appels, emails, notes), organise le portefeuille de prospects et
aide à décider quelle action effectuer ensuite.

Statut : **prototype local** (Streamlit + SQLite), version 0.3.0.

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
- Streamlit (testé avec 1.67.0), Pandas (testé avec 3.1.1)

## Structure

| Fichier | Rôle |
|---|---|
| `main.py` | Interface Streamlit (navigation, pages, formulaires) |
| `database.py` | Accès à la base SQLite : création des tables et toutes les fonctions de lecture/écriture |
| `revora.db` | Base SQLite locale. **Ne jamais la supprimer.** |
| `backups/` | Copies horodatées des fichiers et de la base, faites avant chaque modification importante |
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
| Overview | Fonctionnel (compteurs réels depuis SQLite) |
| Prospects | Liste fonctionnelle (lecture seule) |
| Prospect Details | Fonctionnel : coordonnées, compteurs, ajout d'interactions, timeline, relances |
| Prospecting Pipeline, Activity, Objections, AI Copilot, Performance | Pages vides (à venir) |

## Base de données

Tables : `companies`, `contacts`, `interactions`, `scores`, `tasks`, `integrations`.
Le chemin de la base est calculé à partir de l'emplacement de `database.py`,
donc l'app utilise toujours `~/Documents/REVORA/revora.db`, quel que soit le dossier d'où on la lance.

## Sauvegarder la base

```bash
sqlite3 revora.db ".backup backups/revora-$(date +%Y%m%d-%H%M%S).db"
```
