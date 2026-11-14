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
    assert prospect["status"] == "A prospecter"


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
