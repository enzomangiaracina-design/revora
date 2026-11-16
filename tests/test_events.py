"""Tests des fondations mémoire (phase 13) : auteur des actions, date de réalisation, journal."""

import sqlite3
from datetime import date, datetime, timedelta

import pytest

import database
from core import event_service
from core.activity_service import log_interaction
from core.objection_service import record_objection
from core.prospect_service import update_prospect


@pytest.fixture
def lea(temp_db):
    database.add_user("Léa Martin", "SDR")
    return database.get_users()[0]["id"]


def _rows(table):
    connection = database.get_connection()
    rows = [dict(r) for r in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
    connection.close()
    return rows


def test_author_is_saved_on_every_action(thomas, lea):
    ok, _ = log_interaction(thomas, {
        "channel": "Call", "direction": "Outbound", "event_type": "Completed",
        "subject": "Discovery", "content": "Pas de budget", "outcome": "Rappeler",
        "occurred_at": datetime.now() - timedelta(hours=1),
        "follow_up_date": date.today() + timedelta(days=3),
        "objection_category": "No budget",
    }, created_by=lea)
    assert ok

    assert _rows("interactions")[0]["created_by"] == lea
    assert _rows("objections")[0]["created_by"] == lea
    assert _rows("tasks")[0]["created_by"] == lea

    database.set_prospect_stage(thomas, "In contact", created_by=lea)
    assert _rows("stage_changes")[-1]["created_by"] == lea

    record_objection(thomas, "Bad timing", created_by=lea)
    assert _rows("objections")[-1]["created_by"] == lea


def test_stage_change_by_edit_keeps_author(thomas, lea):
    prospect = database.get_prospect_by_id(thomas)
    ok, _ = update_prospect(thomas, {
        "first_name": "Thomas", "last_name": "Martins", "company_name": "AlphaEngine",
        "vertical": "SaaS", "email": prospect["email"], "phone": prospect["phone"],
        "job_title": "Head of Sales", "status": "Interested",
    }, created_by=lea)
    assert ok
    assert _rows("stage_changes")[-1]["created_by"] == lea


def test_author_is_optional_for_older_calls(thomas):
    database.add_interaction(thomas, "Note", "Internal", "Other", "Note", "x", "")
    database.create_task(thomas, "Rappeler", "", "2026-11-20")

    assert _rows("interactions")[0]["created_by"] is None          # inconnu, pas d'erreur
    assert _rows("tasks")[0]["created_by"] is None


def test_completed_at_is_set_once(thomas):
    database.create_task(thomas, "Rappeler", "", "2026-11-20")
    task_id = database.get_tasks(thomas)[0]["id"]
    assert database.get_tasks(thomas)[0]["completed_at"] is None

    database.complete_task(task_id)
    first = database.get_tasks(thomas)[0]["completed_at"]
    assert first

    connection = database.get_connection()
    connection.execute("UPDATE tasks SET completed_at = '2026-01-01 10:00:00' WHERE id = ?", (task_id,))
    connection.commit()
    connection.close()

    database.complete_task(task_id)                                  # déjà faite : date conservée
    assert database.get_tasks(thomas)[0]["completed_at"] == "2026-01-01 10:00:00"


def test_record_and_read_events(thomas, lea):
    event_id = event_service.record("ai_objection_dismissed", lea, contact_id=thomas,
                                    details={"category": "No budget", "wording": "Pas de budget"})
    event_service.record("task_completed", None, object_id=7, contact_id=thomas)

    events = event_service.history()
    assert [e["action"] for e in events] == ["task_completed", "ai_objection_dismissed"]

    dismissed = event_service.history(user_id=lea)[0]
    assert dismissed["id"] == event_id
    assert dismissed["object_type"] is None
    assert dismissed["details"] == {"category": "No budget", "wording": "Pas de budget"}
    assert dismissed["created_at_local"]

    assert event_service.history(action="task_completed")[0]["object_type"] == "task"
    assert event_service.history(contact_id=thomas, limit=1)[0]["action"] == "task_completed"


def test_unknown_event_is_refused(temp_db):
    with pytest.raises(ValueError):
        event_service.record("something_else", None)

    assert event_service.history() == []


def test_migration_keeps_existing_data(tmp_path, monkeypatch):
    """Une base d'avant la phase 13 garde ses lignes ; les nouvelles colonnes sont vides."""

    old = tmp_path / "old.db"
    connection = sqlite3.connect(old)
    connection.executescript("""
        CREATE TABLE contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
            first_name TEXT NOT NULL, last_name TEXT NOT NULL, email TEXT, phone TEXT,
            job_title TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id INTEGER NOT NULL,
            title TEXT NOT NULL, description TEXT, due_at TEXT, status TEXT DEFAULT 'A faire',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO contacts (first_name, last_name) VALUES ('Ana', 'Lopez');
        INSERT INTO tasks (contact_id, title, status) VALUES (1, 'Ancienne', 'Terminee');
    """)
    connection.commit()
    connection.close()

    monkeypatch.setattr(database, "DATABASE_PATH", old)
    database.initialize_database()
    database.initialize_database()                                   # relancer ne casse rien

    task = _rows("tasks")[0]
    assert task["title"] == "Ancienne" and task["status"] == "Terminee"
    assert task["created_by"] is None and task["completed_at"] is None
    assert _rows("activity_events") == []


def test_done_button_saves_who_completed_the_follow_up(thomas, lea):
    """Écran réel (sans navigateur) : « Done » date la relance et note l'utilisateur actif."""

    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    database.create_task(thomas, "Rappeler Thomas", "", date.today().isoformat())
    task_id = database.get_tasks(thomas)[0]["id"]

    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "main.py"), default_timeout=60)
    at.session_state["user"] = lea                       # « Signed in as » : Léa
    at.session_state["prospect_open"] = True             # fiche de Thomas ouverte
    at.session_state["details_prospect"] = thomas
    at.run()
    at.button(key=f"next_done_{task_id}").click().run()
    assert not at.exception

    assert database.get_tasks(thomas)[0]["completed_at"]
    event = event_service.history(action="task_completed")[0]
    assert (event["user_id"], event["object_id"], event["contact_id"]) == (lea, task_id, thomas)


def test_ai_suggestions_add_and_dismiss_are_logged(thomas, lea, monkeypatch):
    """Écran réel, IA simulée (aucun appel réel) : Add et Dismiss sont notés au journal."""

    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    import screens.prospect_details
    from core import copilot_service

    notes = "Il a dit : « Pas avant mars. » Puis : « Trop cher pour nous. »"
    call = database.add_interaction(thomas, "Call", "Outbound", "Completed", "Discovery", notes, "",
                                    occurred_at="2026-11-10 14:00:00")
    database.set_setting(copilot_service.SETTING_ENABLED, True)
    monkeypatch.setattr(screens.prospect_details, "ai_is_configured", lambda: True)
    monkeypatch.setattr(screens.prospect_details, "ai_generate", lambda *args: (
        {"objections": [
            {"interaction": f"I{call}", "category": "Bad timing", "wording": "Pas avant mars.", "why": ""},
            {"interaction": f"I{call}", "category": "Price too high", "wording": "Trop cher pour nous.", "why": ""},
        ]},
        {"input_tokens": 100, "output_tokens": 50, "model": "test-model"},
    ))

    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "main.py"), default_timeout=60)
    at.session_state["user"] = lea
    at.session_state["prospect_open"] = True
    at.session_state["details_prospect"] = thomas
    at.run()
    at.button(key=f"ai_objections_btn_{thomas}").click().run()
    at.selectbox(key=f"ai_objection_category_{thomas}_0").set_value("No budget").run()   # catégorie corrigée
    at.button(key=f"ai_objection_add_{thomas}_0").click().run()
    at.button(key=f"ai_objection_dismiss_{thomas}_1").click().run()
    assert not at.exception

    accepted = event_service.history(action="ai_objection_accepted")[0]
    assert accepted["user_id"] == lea and accepted["contact_id"] == thomas
    assert accepted["details"]["suggested_category"] == "Bad timing"
    assert accepted["details"]["category"] == "No budget"

    dismissed = event_service.history(action="ai_objection_dismissed")[0]
    assert dismissed["details"]["wording"] == "Trop cher pour nous."

    saved = _rows("objections")[0]
    assert (saved["category"], saved["source"], saved["created_by"]) == ("No budget", "ai", lea)
