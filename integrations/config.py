"""Lecture des secrets (jetons d'accès) depuis les variables d'environnement.

Les secrets ne sont JAMAIS écrits dans le code ni dans la base : ils sont
placés dans le fichier .env (exclu de Git) ou exportés dans le terminal.

Ce petit lecteur de .env évite d'ajouter une dépendance (python-dotenv).
Il ne remplace jamais une variable déjà définie dans le terminal.
"""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path=ENV_PATH):
    """Charge les lignes CLE=VALEUR d'un fichier .env dans os.environ."""

    path = Path(path)

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")

        if key and value:
            os.environ.setdefault(key, value)


def get_secret(name):
    """Retourne la valeur d'une variable d'environnement, ou None si absente/vide."""

    load_env_file()

    return os.environ.get(name) or None
