"""Sauvegardes de la base REVORA en ligne de commande (phase 12.3).

Utilisation (base par défaut : revora.db, ou celle de REVORA_DATABASE) :
    python3 backup_db.py                 # sauvegarde maintenant
    python3 backup_db.py --list          # liste les sauvegardes automatiques
    python3 backup_db.py --restore FICHIER --yes
                                         # restaure : la base actuelle est d'abord sauvegardée

Sans --yes, la restauration se contente d'expliquer ce qu'elle ferait.
"""

import sys
from pathlib import Path

import database
from core.backup_service import backup_now, list_backups, restore


def main(argv):
    db = database.DATABASE_PATH

    if "--list" in argv:
        backups = list_backups(db)
        print(f"{len(backups)} automatic backup(s) of {db.name}:" if backups else f"No automatic backup of {db.name}.")
        for moment, path in backups:
            print(f"  {moment:%d/%m/%Y %H:%M:%S}  {path}")
        return 0

    if "--restore" in argv:
        index = argv.index("--restore") + 1
        if index >= len(argv):
            print("Give the backup file to restore: python3 backup_db.py --restore FILE --yes")
            return 1

        if not argv[index].strip() or argv[index].startswith("--"):
            print("Give the backup file to restore: python3 backup_db.py --restore FILE --yes")
            return 1

        source = Path(argv[index])
        if "--yes" not in argv:
            print(f"This would replace the content of {db.name} with {source.name}.\n"
                  f"The current {db.name} would first be saved in backups/auto/.\n"
                  "Add --yes to do it.")
            return 1

        try:
            safety = restore(source, db)
        except (FileNotFoundError, ValueError) as error:
            print(f"Nothing done: {error}")
            return 1

        print(f"Restored {source.name} into {db.name}."
              + (f"\nThe previous content was saved in {safety}." if safety else ""))
        return 0

    try:
        print(f"Backup saved: {backup_now(db)}")
    except FileNotFoundError as error:
        print(f"Nothing done: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
