"""Journal des erreurs (phase 12.3).

Chaque erreur inattendue est ajoutée à logs/errors.log, à côté de la base, avec la
date, l'endroit et le détail technique. Le fichier tourne : au-delà de 1 Mo, il
devient errors.log.1 (3 fichiers gardés au plus). Le dossier logs/ est exclu de Git.

Les messages d'erreur peuvent contenir des données de la base : le journal reste
sur la machine, comme la base elle-même.
"""

import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_BYTES = 1_000_000
BACKUPS = 3


def log_path(db_path):
    """Fichier du journal : <dossier de la base>/logs/errors.log."""

    return Path(db_path).parent / "logs" / "errors.log"


def _logger(path):
    """Un « logger » par fichier, créé une seule fois (pas de lignes en double)."""

    logger = logging.getLogger(f"revora.errors.{path}")

    if not logger.handlers:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        logger.propagate = False                      # pas de doublon dans la console

    return logger


def record(error, where, db_path):
    """Ajoute l'erreur au journal. Retourne le texte technique (pour l'affichage).

    Ne lève jamais d'exception : un journal impossible à écrire ne doit pas
    aggraver la panne qu'il décrit.
    """

    details = "".join(traceback.format_exception(error))

    try:
        _logger(log_path(db_path)).error("%s\n%s", where, details.rstrip())
    except Exception:
        pass

    return details


def recent_errors(db_path, limit=20):
    """Dernières entrées du journal (les plus récentes d'abord) : [(date, endroit, détail)]."""

    path = log_path(db_path)

    if not path.exists():
        return []

    entries, current = [], None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if " | " in line[:30] and line[:4].isdigit():          # « 2026-11-16 09:50:01,123 | page »
            stamp, _, where = line.partition(" | ")
            current = [stamp[:19], where, []]
            entries.append(current)
        elif current is not None:
            current[2].append(line)

    return [(stamp, where, "\n".join(lines)) for stamp, where, lines in reversed(entries)][:limit]
