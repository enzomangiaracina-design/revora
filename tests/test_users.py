"""Tests de l'équipe (phase 11.1) : utilisateurs, rôles, propriétaires."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import database
from core.user_service import (
    create_user,
    find_user,
    import_owners,
    missing_owners,
    owner_choices,
    set_active,
    set_role,
)

MAIN = str(Path(__file__).resolve().parent.parent / "main.py")


def test_create_user_validates_and_refuses_duplicates(temp_db):
    assert create_user("  Léa   Martin ", "SDR")[0]
    assert database.get_users()[0]["name"] == "Léa Martin"          # espaces nettoyés

    assert not create_user("léa martin", "SDR")[0]                   # même nom, autre casse
    assert not create_user("L", "SDR")[0]
    assert not create_user("Hugo", "CEO")[0]                         # rôle inconnu
    assert len(database.get_users()) == 1


def test_role_and_deactivation_keep_the_user(temp_db):
    create_user("Hugo Bernard", "SDR")
    user_id = database.get_users()[0]["id"]

    assert set_role(user_id, "Manager")[0]
    assert not set_role(user_id, "Boss")[0]
    assert set_active(user_id, False)[0]

    user = database.get_users()[0]
    assert user["role"] == "Manager" and user["active"] == 0       # désactivé, pas supprimé
    assert database.get_users(active_only=True) == []
    assert not set_active(999, True)[0]


def test_import_owners_adds_team_without_touching_prospects(thomas):
    database.create_prospect("Anna", "Petit", "Beta", "SaaS", "anna@example.com", "", "CFO", owner="Léa Martin")
    database.create_prospect("Paul", "Roy", "Beta", "SaaS", "paul@example.com", "", "CTO", owner="léa martin")
    before = database.get_all_prospects()

    assert [n.casefold() for n in missing_owners([], before)] == ["léa martin"]   # un seul nom, sans doublon
    ok, message = import_owners([], before)

    assert ok and "1 user(s) added" in message
    assert [u["name"].casefold() for u in database.get_users()] == ["léa martin"]
    assert database.get_all_prospects() == before                  # prospects inchangés
    assert import_owners(database.get_users(), before)[1].startswith("Every sales owner")


def test_owner_choices_keep_the_current_owner():
    users = [{"name": "Léa Martin", "active": 1}, {"name": "Old Rep", "active": 0}]

    assert owner_choices(users) == ["", "Léa Martin"]                  # "" = non assigné, inactif masqué
    assert owner_choices(users, "Old Rep") == ["", "Léa Martin", "Old Rep"]
    assert owner_choices(users, "léa martin") == ["", "Léa Martin"]
    assert find_user(users, "LÉA MARTIN")["name"] == "Léa Martin"


def test_signed_in_as_menu(temp_db):
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert not [s for s in at.sidebar.selectbox if s.label == "Signed in as"]     # pas d'équipe : pas de menu

    create_user("Léa Martin", "SDR")
    create_user("Nina Roy", "Manager")
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    menu = next(s for s in at.sidebar.selectbox if s.label == "Signed in as")
    assert menu.value is None
    menu.select(database.get_users()[1]["id"]).run()
    assert not at.exception

    at.sidebar.radio[0].set_value("Settings").run()
    assert not at.exception
    assert any("Team" == h.value for h in at.subheader)
