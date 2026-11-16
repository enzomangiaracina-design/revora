"""Démarrage de REVORA sur Render (phase 12.2, pilote — données de démonstration uniquement).

Étapes, à chaque démarrage :
  1. vérifie que la base vise le disque permanent (REVORA_DATABASE, chemin absolu) ;
  2. crée la base de démonstration fictive si elle n'existe pas encore (jamais d'écrasement) ;
  3. garantit que REVORA_ADMIN_EMAIL est un manager actif (sinon personne ne pourrait entrer) ;
  4. lance Streamlit sur 0.0.0.0:$PORT, avec les secrets de Render (/etc/secrets/secrets.toml).

Ce script ne fait rien de plus et ne contacte aucun service externe.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = "/etc/secrets/secrets.toml"      # emplacement des « Secret Files » de Render


def prepare(environ):
    """Étapes 1 à 3. Retourne la liste des messages (affichés dans les logs de Render)."""

    target = environ.get("REVORA_DATABASE", "").strip()
    if not target or not Path(target).is_absolute():
        raise SystemExit("REVORA_DATABASE must be an absolute path on the persistent disk.")

    sys.path.insert(0, str(ROOT))
    import database
    import seed_demo
    from core.user_service import ensure_admin

    messages = []
    seed_demo.main(["--path", target, "--if-missing"])

    database.DATABASE_PATH = Path(target)
    database.initialize_database()

    if environ.get("REVORA_ADMIN_EMAIL", "").strip():
        messages.append(ensure_admin(environ["REVORA_ADMIN_EMAIL"], environ.get("REVORA_ADMIN_NAME"))[1])
    else:
        messages.append("REVORA_ADMIN_EMAIL is not set: no administrator created.")

    return messages


def streamlit_command(environ):
    """Commande Streamlit pour Render."""

    return [
        "streamlit", "run", str(ROOT / "main.py"),
        "--server.port", environ.get("PORT", "10000"),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--secrets.files", SECRETS_FILE,
    ]


if __name__ == "__main__":
    for message in prepare(os.environ):
        print(message, flush=True)

    command = streamlit_command(os.environ)
    os.chdir(ROOT)
    os.execvp(command[0], command)            # Streamlit remplace ce script (un seul processus)
