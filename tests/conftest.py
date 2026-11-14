"""Configuration partagée des tests.

Concept : une "fixture" pytest prépare un environnement avant chaque test.
Ici, `temp_db` redirige database.py vers une base SQLite TEMPORAIRE et vide.
Les tests ne touchent donc JAMAIS le vrai fichier revora.db.
"""

import pytest

import database


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Fournit une base de test vide, supprimée automatiquement après le test."""

    test_path = tmp_path / "test_revora.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_path)
    database.initialize_database()

    return test_path


@pytest.fixture
def thomas(temp_db):
    """Crée un prospect de test et retourne son identifiant."""

    database.create_prospect(
        "Thomas", "Martins", "AlphaEngine", "SaaS",
        "thomas.martin@example.com", "0612345678", "Head of Sales",
    )

    return database.get_all_prospects()[0]["id"]
