"""Sauvegardes automatiques de la base (phase 12.3).

Principe :
  - une copie par jour, faite au premier affichage de la journée, dans
    backups/auto/<nom de la base>/ (ex. backups/auto/revora/) ;
  - la copie utilise l'API « backup » de SQLite : elle est cohérente même si
    l'application écrit en même temps (contrairement à une simple copie de fichier) ;
  - seules les KEEP copies automatiques les plus récentes sont gardées. Les autres
    sauvegardes (backups/<date-heure>/, faites avant chaque modification) ne sont
    jamais touchées ;
  - la restauration ne supprime rien : elle sauvegarde d'abord la base actuelle,
    puis recopie la sauvegarde choisie par-dessus.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

KEEP = 14                       # copies automatiques conservées (deux semaines)
PREFIX = "auto-"
STAMP = "%Y%m%d-%H%M%S"


def backup_dir(db_path, root=None):
    """Dossier des sauvegardes automatiques d'une base : <racine>/backups/auto/<nom>/."""

    db_path = Path(db_path)
    root = Path(root) if root else db_path.parent

    return root / "backups" / "auto" / db_path.stem


def list_backups(db_path, root=None):
    """Sauvegardes automatiques, de la plus récente à la plus ancienne : [(datetime, Path)]."""

    folder = backup_dir(db_path, root)

    if not folder.exists():
        return []

    found = []
    for path in folder.glob(f"{PREFIX}*.db"):
        try:
            found.append((datetime.strptime(path.stem[len(PREFIX):], STAMP), path))
        except ValueError:
            continue                                   # fichier étranger : ignoré, jamais supprimé

    return sorted(found, reverse=True)


def _copy(source, target):
    """Copie cohérente d'une base SQLite vers un fichier (API backup de SQLite)."""

    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    src.close()
    dst.close()


def backup_now(db_path, root=None, now=None, keep=KEEP):
    """Sauvegarde la base maintenant, puis supprime les copies AUTOMATIQUES en trop.

    Retourne le chemin de la nouvelle sauvegarde.
    """

    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path.name}")

    folder = backup_dir(db_path, root)
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / f"{PREFIX}{(now or datetime.now()).strftime(STAMP)}.db"
    _copy(db_path, target)

    for _, old in list_backups(db_path, root)[keep:]:
        old.unlink()                                   # uniquement des copies auto-AAAAMMJJ-HHMMSS.db

    return target


def daily_backup(db_path, root=None, now=None, keep=KEEP):
    """Sauvegarde si aucune copie automatique n'existe encore aujourd'hui.

    Retourne le chemin de la sauvegarde créée, ou None (déjà faite, ou base absente).
    """

    now = now or datetime.now()
    existing = list_backups(db_path, root)

    if not Path(db_path).exists() or (existing and existing[0][0].date() == now.date()):
        return None

    return backup_now(db_path, root, now, keep)


def restore(backup_path, db_path, root=None, now=None):
    """Remplace le contenu de la base par celui d'une sauvegarde.

    Sécurité : la base actuelle est d'abord sauvegardée (copie automatique datée),
    et ne peut pas être perdue. Retourne le chemin de cette copie de sécurité.
    """

    if not str(backup_path or "").strip():
        raise ValueError("Give the backup file to restore.")

    backup_path, db_path = Path(backup_path), Path(db_path)

    # Un vrai FICHIER est exigé : un chemin vide ou un dossier (« . ») est refusé
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    if backup_path.resolve() == db_path.resolve():
        raise ValueError("Choose a backup file, not the database itself.")

    # Refuse un fichier qui n'est pas une base SQLite saine (ouvert en lecture seule)
    try:
        check = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        healthy = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        check.close()
    except sqlite3.Error:
        healthy = False

    if not healthy:
        raise ValueError(f"{backup_path.name} is not a valid REVORA database: restore refused.")

    safety = backup_now(db_path, root, now, keep=KEEP + 1) if db_path.exists() else None
    _copy(backup_path, db_path)

    return safety
