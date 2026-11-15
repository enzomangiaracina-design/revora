"""Tests de persistance de database.py (sur une base temporaire)."""

import ast
import sqlite3
from pathlib import Path

import database

EXPECTED_TABLES = {"companies", "contacts", "interactions", "scores", "tasks", "integrations"}


def test_main_imports_exist():
    """Chaque fonction importée par main.py doit exister dans database.py.

    C'est exactement le test qui aurait détecté l'erreur get_prospect_by_id.
    """

    source = (Path(database.__file__).parent / "main.py").read_text()

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "database":
            for alias in node.names:
                assert hasattr(database, alias.name), f"{alias.name} manquant"


def test_tables_are_created(temp_db):
    connection = sqlite3.connect(temp_db)
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    connection.close()

    assert EXPECTED_TABLES <= tables


def test_initialize_twice_keeps_data(thomas):
    """Relancer l'initialisation ne doit jamais effacer les données."""

    database.initialize_database()

    assert len(database.get_all_prospects()) == 1


def test_prospect_is_saved_and_read_back(thomas):
    prospect = database.get_prospect_by_id(thomas)

    assert prospect["first_name"] == "Thomas"
    assert prospect["company_name"] == "AlphaEngine"
    assert prospect["vertical"] == "SaaS"
    assert prospect["status"] == "To prospect"


def test_unknown_prospect_returns_none(temp_db):
    assert database.get_prospect_by_id(9999) is None


def test_interaction_is_saved(thomas):
    database.add_interaction(
        thomas, "Call", "Outbound", "No answer", "Premier appel", "Messagerie", "Rappeler mardi"
    )

    interactions = database.get_interactions(thomas)

    assert len(interactions) == 1
    assert interactions[0]["channel"] == "Call"
    assert interactions[0]["provider"] == "manual"


def test_task_lifecycle(thomas):
    database.create_task(thomas, "Rappeler Thomas", "", "2026-11-18")

    task = database.get_tasks(thomas)[0]
    assert task["status"] == "A faire"

    database.complete_task(task["id"])
    assert database.get_tasks(thomas)[0]["status"] == "Terminee"


# ---------- Phase 2 : migration, modification, suppression ----------

OLD_SCHEMA = """
CREATE TABLE companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    vertical TEXT, website TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
    first_name TEXT NOT NULL, last_name TEXT NOT NULL, email TEXT, phone TEXT,
    job_title TEXT, status TEXT DEFAULT 'To prospect', hubspot_id TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
INSERT INTO companies (name, vertical) VALUES ('AlphaEngine', 'SaaS');
INSERT INTO contacts (company_id, first_name, last_name, email)
    VALUES (1, 'Thomas', 'Martins', 'thomas.martin@example.com');
"""


def test_migration_adds_columns_and_keeps_data(tmp_path, monkeypatch):
    """Une base au format de la version 0.3 doit être migrée sans perte."""

    old_db = tmp_path / "old.db"
    connection = sqlite3.connect(old_db)
    connection.executescript(OLD_SCHEMA)
    connection.close()

    monkeypatch.setattr(database, "DATABASE_PATH", old_db)
    database.initialize_database()
    database.initialize_database()  # une deuxième fois : rien ne doit casser

    connection = sqlite3.connect(old_db)
    contact_columns = {row[1] for row in connection.execute("PRAGMA table_info(contacts)")}
    company_columns = {row[1] for row in connection.execute("PRAGMA table_info(companies)")}
    connection.close()

    assert {"source", "owner", "updated_at"} <= contact_columns
    assert {"industry", "size", "country"} <= company_columns

    prospect = database.get_all_prospects()[0]
    assert prospect["first_name"] == "Thomas"
    assert prospect["company_name"] == "AlphaEngine"
    assert prospect["source"] is None


def test_update_prospect(thomas):
    ok, _ = database.update_prospect(
        thomas, "Thomas", "Martin", "AlphaEngine", "SaaS",
        "thomas.martin@example.com", "0612345678", "VP Sales", "In contact",
        source="Salon", owner="Enzo",
    )

    prospect = database.get_prospect_by_id(thomas)
    assert ok
    assert prospect["last_name"] == "Martin"
    assert prospect["job_title"] == "VP Sales"
    assert prospect["status"] == "In contact"
    assert prospect["source"] == "Salon"
    assert prospect["updated_at"] is not None


def test_update_rejects_email_of_another_contact(thomas):
    database.create_prospect("Julie", "Durand", "Beta", "SaaS", "julie@example.com", None, None)

    ok, message = database.update_prospect(
        thomas, "Thomas", "Martins", "AlphaEngine", "SaaS",
        "JULIE@example.com", None, None, "To prospect",
    )

    assert not ok
    assert database.get_prospect_by_id(thomas)["email"] == "thomas.martin@example.com"


def test_update_can_move_to_new_company(thomas):
    database.update_prospect(
        thomas, "Thomas", "Martins", "NewCo", "Finance", None, None, None, "To prospect"
    )

    prospect = database.get_prospect_by_id(thomas)
    assert prospect["company_name"] == "NewCo"
    assert prospect["vertical"] == "Finance"
    assert database.get_verticals() == ["Finance", "SaaS"]


def test_delete_prospect_removes_linked_data(thomas):
    interaction_id = database.add_interaction(thomas, "Call", "Outbound", "Objection", "", "x", "")
    database.create_task(thomas, "Rappeler", "", "2026-11-18")
    database.add_objection(thomas, "No budget", interaction_id=interaction_id)

    assert database.count_prospect_activity(thomas) == {
        "interactions": 1, "tasks": 1, "scores": 0, "objections": 1,
    }

    deleted = database.delete_prospect(thomas)

    assert deleted == {"objections": 1, "interactions": 1, "tasks": 1, "scores": 0,
                       "stage_changes": 0, "focus_snoozes": 0, "contacts": 1}
    assert database.get_objections() == []
    assert database.get_prospect_by_id(thomas) is None
    assert database.get_interactions(thomas) == []
    assert database.get_verticals() == ["SaaS"]  # l'entreprise est conservée


def test_empty_vertical_does_not_duplicate_company(temp_db):
    database.create_prospect("A", "One", "Gamma", None, None, None, None)
    database.create_prospect("B", "Two", "Gamma", "", None, None, None)

    connection = sqlite3.connect(temp_db)
    assert connection.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
    connection.close()


def test_prospect_without_stage_goes_to_the_real_first_stage(temp_db):
    """Une base existante garde ses étapes (ex. en français) : pas de nom écrit en dur."""

    first = database.get_stages()[0]
    database.rename_stage(first["id"], "A prospecter")

    database.create_prospect("Ana", "Lopez", "Acme", "SaaS", None, None, None)

    assert database.get_all_prospects()[0]["status"] == "A prospecter"
    assert "To prospect" not in database.get_stage_names()      # aucune étape fantôme ajoutée
