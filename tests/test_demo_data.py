"""Tests de la base de démonstration (données fictives, base séparée)."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import database
from core.demo_data import PEOPLE, generate_demo

TODAY = date(2026, 11, 15)
MAIN = str(Path(__file__).resolve().parent.parent / "main.py")


def rows(path, query):
    connection = sqlite3.connect(path)
    result = connection.execute(query).fetchall()
    connection.close()
    return result


def test_demo_is_created_in_a_separate_file(tmp_path):
    before = database.DATABASE_PATH
    summary = generate_demo(tmp_path / "demo.db", today=TODAY)

    assert summary["prospects"] == len(PEOPLE) == 20
    assert summary["interactions"] > 50 and summary["objections"] >= 5 and summary["follow_ups"] >= 10
    assert database.DATABASE_PATH == before                     # la base de l'application n'a pas changé


def test_demo_is_fictitious_and_in_the_past(tmp_path):
    path = tmp_path / "demo.db"
    generate_demo(path, today=TODAY)

    emails = [r[0] for r in rows(path, "SELECT email FROM contacts")]
    assert all(email.endswith(".example") for email in emails)          # domaine réservé, jamais réel
    moments = [r[0] for r in rows(path, "SELECT datetime(occurred_at, 'localtime') FROM interactions")]
    assert max(datetime.fromisoformat(m) for m in moments).date() <= TODAY
    overdue = rows(path, f"SELECT count(*) FROM tasks WHERE status = 'A faire' AND due_at < '{TODAY}'")[0][0]
    assert overdue >= 1                                                 # de quoi remplir Today's focus


def test_demo_is_deterministic(tmp_path):
    first, second = tmp_path / "a.db", tmp_path / "b.db"
    generate_demo(first, today=TODAY)
    generate_demo(second, today=TODAY)

    query = "SELECT channel, event_type, subject, occurred_at FROM interactions ORDER BY id"
    assert rows(first, query) == rows(second, query)


def test_never_writes_into_revora_db():
    with pytest.raises(ValueError, match="revora.db"):
        generate_demo(database.DEFAULT_DATABASE_PATH, today=TODAY)


def test_existing_demo_needs_reset(tmp_path):
    path = tmp_path / "demo.db"
    generate_demo(path, today=TODAY)

    with pytest.raises(FileExistsError):
        generate_demo(path, today=TODAY)

    assert generate_demo(path, today=TODAY, reset=True)["prospects"] == 20


def test_database_path_can_be_chosen_by_environment(monkeypatch):
    monkeypatch.setenv("REVORA_DATABASE", "demo.db")
    assert database._database_path() == database.BASE_DIR / "demo.db"

    monkeypatch.setenv("REVORA_DATABASE", "")
    assert database._database_path() == database.DEFAULT_DATABASE_PATH


def test_every_page_renders_on_the_demo(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    generate_demo(path)
    monkeypatch.setattr(database, "DATABASE_PATH", path)

    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert any("Demo database" in w.value for w in at.sidebar.warning)

    for label in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(label).run()
        assert not at.exception, (label, [e.value for e in at.exception])


def test_demo_dates_are_consistent(tmp_path):
    path = tmp_path / "demo.db"
    generate_demo(path, today=TODAY)

    # Une relance est planifiée avant son échéance ; un prospect est ajouté avant son premier échange
    late = rows(path, "SELECT count(*) FROM tasks WHERE date(created_at, 'localtime') > due_at")[0][0]
    assert late == 0
    before_contact = rows(path, """
        SELECT count(*) FROM contacts c
        WHERE c.created_at > (SELECT min(i.occurred_at) FROM interactions i WHERE i.contact_id = c.id)""")[0][0]
    assert before_contact == 0


def test_backdating_is_refused_on_revora_db_and_other_tables(temp_db, monkeypatch):
    with pytest.raises(ValueError, match="Table not allowed"):
        database.set_created_at("interactions", 1, "2026-01-01 10:00:00")

    monkeypatch.setattr(database, "DATABASE_PATH", database.DEFAULT_DATABASE_PATH)
    with pytest.raises(ValueError, match="outside revora.db"):
        database.set_created_at("contacts", 1, "2026-01-01 10:00:00")
