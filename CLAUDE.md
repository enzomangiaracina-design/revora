# CLAUDE.md — Règles du projet REVORA

## Contexte
- SaaS de prospection outbound pour SDR/BDR. Prototype Streamlit + SQLite, Python.
- Le développeur débute en programmation : expliquer chaque modification, les concepts utilisés, et donner les commandes de lancement.
- Langue de communication : français. **Interface de l'application : anglais** (écrans, messages, aides) ; code et commentaires en français.

## Règles absolues
- **Ne jamais supprimer `revora.db`.**
- Avant toute migration ou modification importante : copie horodatée des fichiers et de la base dans `backups/<date-heure>/` (utiliser `sqlite3 revora.db ".backup ..."`).
- Ne jamais écraser ou modifier les données de démonstration sans autorisation.
- Tester sur une **copie** de la base, jamais sur `revora.db` directement.
- Toujours lire les fichiers réellement présents sur le disque avant de les modifier ; ne pas se fier aux versions échangées précédemment.
- Ne pas annoncer qu'une fonctionnalité marche sans l'avoir exécutée.
- Ne jamais inventer une intégration ni prétendre qu'une API (HubSpot, Gmail, Noota, LinkedIn) fonctionne sans l'avoir vérifiée.
- Pas de scraping LinkedIn ni d'automatisation contraire à ses conditions.
- Ne pas changer de stack (ex. Streamlit → React/Next.js) sans présenter les avantages et obtenir une validation.
- Ne jamais utiliser de données réelles (Noota, employeur) sans autorisation. Secrets dans `.env` (exclu de Git), modèle dans `.env.example`.

## Méthode
- Modifier les fichiers existants, éviter les réécritures complètes.
- Corriger uniquement les problèmes identifiés ; pas de fonctionnalité non demandée.
- À chaque étape, indiquer : ce qui a changé, pourquoi, fichiers concernés, tests effectués, problèmes restants.
- Mettre à jour `CHANGELOG.md` à chaque modification, `ROADMAP.md` quand une phase avance, `README.md` si le lancement ou la structure change.

## Architecture
- Identité visuelle : couleurs, police et rayons dans `.streamlit/config.toml` ; jetons et CSS complémentaire dans `ui/theme.py`. Ne jamais ajouter de couleur, rayon, effet ou style d'icône ailleurs (règle du brand kit). Le violet est réservé aux actions, à la navigation active et à la sélection ; vert/orange/rouge/bleu aux états.
  Palette de référence : le brand kit (`REVORA_Brand_Kit`), avec le gris secondaire lisible `#9295A1` repris du cahier des charges (contraste ≥ 4,5).
- `database.py` : toute la logique SQL. L'interface (`main.py`, `screens/`) n'exécute jamais de SQL directement.
- `main.py` : configuration, données communes (`AppContext`), navigation et aiguillage — rien d'autre.
- `screens/` : une page = un module avec `render(ctx)` ; outils d'interface communs dans `screens/shared.py`,
  imports communs dans `screens/common.py`. Modifier une page = modifier son module, sans toucher aux autres.
- États vides : toujours `empty_state` / `no_results` (`screens/shared.py`) avec une action pour continuer ; ne pas réintroduire de `st.info` ad hoc.
- Ne pas créer de dossier `pages/` : Streamlit le transforme automatiquement en navigation multipage.
- `DATABASE_PATH` est relatif à `database.py` (pas au dossier courant). `REVORA_DATABASE` permet de lancer l'app sur une autre base (ex. `demo.db`, générée par `seed_demo.py`) ; un bandeau l'indique. Le générateur de démo refuse d'écrire dans `revora.db`.
- Équipe (phase 11) : table `users` ; `contacts.owner` reste un NOM (pas d'identifiant). L'utilisateur actif
  (« Signed in as », `ctx.user`) n'est PAS une authentification : pas de mot de passe.
- Vraie connexion (phase 12.1) : `st.login` (OIDC), active seulement si `.streamlit/secrets.toml` contient
  `[auth]` complet (`ctx.auth`). Accès = email d'un membre actif de l'équipe. Jamais de mot de passe
  stocké par REVORA ; `secrets.toml` reste hors de Git.
- Interactions : `UNIQUE(provider, external_id)` garantit l'idempotence des synchronisations futures ; les saisies manuelles utilisent `provider = 'manual'`.
- Les futurs connecteurs suivront l'interface `authenticate / test_connection / fetch_events / normalize_event / sync_events`, découplés du scoring.
- Scoring prévu : global = 0,35 × Fit + 0,40 × Engagement + 0,25 × Intent (pondérations configurables, scores sur 100).

## Tester
Tests automatiques (base temporaire via la fixture `temp_db` de `tests/conftest.py`) :

```bash
python3 -m pytest
```

Tout nouveau code dans `core/` doit avoir ses tests dans `tests/`.

Rendu de toutes les pages sans navigateur (sur une copie de la base) :

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("main.py").run()
at.sidebar.radio[0].set_value("Prospect Details").run()
assert not at.exception
```

Lancement réel : `streamlit run main.py`.
