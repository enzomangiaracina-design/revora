"""Tests des sauvegardes automatiques et du journal des erreurs (phase 12.3)."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import database
from core import backup_service as backups
from core.error_log import log_path, record, recent_errors

MAIN = str(Path(__file__).resolve().parent.parent / "main.py")
NOW = datetime(2026, 11, 16, 9, 30)


def names(db):
    connection = sqlite3.connect(db)
    rows = [r[0] for r in connection.execute("SELECT first_name FROM contacts ORDER BY id")]
    connection.close()
    return rows


def test_backup_is_a_consistent_copy(thomas, temp_db):
    path = backups.backup_now(temp_db, now=NOW)

    assert path == temp_db.parent / "backups" / "auto" / temp_db.stem / "auto-20261116-093000.db"
    assert names(path) == ["Thomas"]


def test_daily_backup_runs_once_a_day(temp_db):
    assert backups.daily_backup(temp_db, now=NOW) is not None
    assert backups.daily_backup(temp_db, now=NOW + timedelta(hours=5)) is None          # même jour
    assert backups.daily_backup(temp_db, now=NOW + timedelta(days=1)) is not None
    assert len(backups.list_backups(temp_db)) == 2


def test_rotation_keeps_recent_copies_and_never_foreign_files(temp_db):
    folder = backups.backup_dir(temp_db)
    folder.mkdir(parents=True)
    foreign = folder / "my-own-copy.db"
    foreign.write_text("keep me")

    for day in range(5):
        backups.backup_now(temp_db, now=NOW + timedelta(days=day), keep=3)

    kept = [moment.day for moment, _ in backups.list_backups(temp_db)]
    assert kept == [20, 19, 18]                                    # les 3 plus récentes
    assert foreign.exists()                                        # jamais supprimé


def test_restore_saves_current_database_first(thomas, temp_db):
    old = backups.backup_now(temp_db, now=NOW)
    database.create_prospect("Anna", "Petit", "Beta", "SaaS", "anna@example.com", "", "CFO")
    assert names(temp_db) == ["Thomas", "Anna"]

    safety = backups.restore(old, temp_db, now=NOW + timedelta(hours=1))

    assert names(temp_db) == ["Thomas"]                            # sauvegarde restaurée
    assert names(safety) == ["Thomas", "Anna"]                     # rien de perdu


def test_restore_refuses_bad_inputs(temp_db, tmp_path):
    damaged = tmp_path / "damaged.db"
    damaged.write_bytes(b"not a database at all" * 100)

    with pytest.raises(ValueError):
        backups.restore(damaged, temp_db)
    with pytest.raises(ValueError):
        backups.restore("", temp_db)                               # chemin vide
    with pytest.raises(FileNotFoundError):
        backups.restore(tmp_path, temp_db)                         # un dossier, pas un fichier
    with pytest.raises(ValueError):
        backups.restore(temp_db, temp_db)
    with pytest.raises(FileNotFoundError):
        backups.restore(tmp_path / "missing.db", temp_db)
    assert backups.list_backups(temp_db) == []                     # rien n'a été touché


def test_error_log_records_and_reads_back(tmp_path):
    db = tmp_path / "x.db"
    try:
        raise ValueError("boom")
    except ValueError as error:
        details = record(error, "Pipeline", db)

    assert "ValueError: boom" in details
    stamp, where, text = recent_errors(db)[0]
    assert where == "Pipeline" and "ValueError: boom" in text and stamp[:4].isdigit()
    assert log_path(db).parent.name == "logs"


def test_app_makes_the_daily_backup_and_shows_it(temp_db):
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert len(backups.list_backups(temp_db)) == 1

    at.sidebar.radio[0].set_value("Settings").run()
    assert not at.exception
    assert any("Last automatic backup" in c.value for c in at.caption)
    # « Back up now » : la dernière sauvegarde contient ce qui vient d'être ajouté
    database.create_prospect("Anna", "Petit", "Beta", "SaaS", "anna@example.com", "", "CFO")
    at.button(key="backup_now").click().run()
    assert not at.exception
    assert names(backups.list_backups(temp_db)[0][1]) == ["Anna"]


def test_command_line_refuses_empty_restore(temp_db, capsys):
    import backup_db

    assert backup_db.main(["--restore", "", "--yes"]) == 1
    assert backup_db.main(["--restore", "--yes"]) == 1
    assert "Give the backup file" in capsys.readouterr().out
    assert backups.list_backups(temp_db) == []                     # aucune action
