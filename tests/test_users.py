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


# ---------- « My prospects » (phase 11.2) ----------

from core.user_service import EVERYONE, MINE, default_scope, for_prospects, owned_by


def test_default_scope_depends_on_role():
    assert default_scope({"role": "SDR"}) == MINE
    assert default_scope({"role": "Manager"}) == EVERYONE
    assert default_scope(None) == EVERYONE


def test_owned_by_and_related_items():
    prospects = [{"id": 1, "owner": "Léa Martin"}, {"id": 2, "owner": " léa martin "},
                 {"id": 3, "owner": "Hugo"}, {"id": 4, "owner": None}]
    mine = owned_by(prospects, "LÉA MARTIN")

    assert [p["id"] for p in mine] == [1, 2]
    assert owned_by(prospects, "") == []
    items = [{"contact_id": 1}, {"contact_id": 3}, {"contact_id": 2}]
    assert for_prospects(items, mine) == [{"contact_id": 1}, {"contact_id": 2}]


def _team_with_prospects():
    create_user("Léa Martin", "SDR")
    create_user("Nina Roy", "Manager")
    database.create_prospect("Anna", "Petit", "Beta", "SaaS", "anna@example.com", "", "CFO", owner="Léa Martin")
    database.create_prospect("Paul", "Roy", "Gamma", "SaaS", "paul@example.com", "", "CTO", owner="Hugo")
    return {u["name"]: u["id"] for u in database.get_users()}


def test_sdr_sees_only_her_prospects_by_default(temp_db):
    ids = _team_with_prospects()
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    next(s for s in at.sidebar.selectbox if s.label == "Signed in as").select(ids["Léa Martin"]).run()

    at.sidebar.radio[0].set_value("Prospects").run()
    assert not at.exception
    assert any("1 of 2 prospects" in c.value and "your prospects only" in c.value for c in at.caption)

    at.sidebar.radio[0].set_value("Prospecting Pipeline").run()
    assert not at.exception
    assert any(c.value.startswith("1 of 2 prospect") for c in at.caption)


def test_manager_sees_everyone_and_choice_is_shared(temp_db):
    ids = _team_with_prospects()
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    next(s for s in at.sidebar.selectbox if s.label == "Signed in as").select(ids["Nina Roy"]).run()

    at.sidebar.radio[0].set_value("Prospects").run()
    assert any(c.value == "2 of 2 prospects" for c in at.caption)

    at.segmented_control(key="prospects_scope").set_value(MINE).run()   # Nina n'a aucun prospect
    assert any(c.value.startswith("0 of 2 prospects") for c in at.caption)

    at.sidebar.radio[0].set_value("Overview").run()                     # même choix sur l'Overview
    assert not at.exception
    assert at.segmented_control(key="overview_scope").value == MINE
    assert any("No prospect assigned to you yet" in m.value for m in at.markdown)


# ---------- Phase 11.3 : Performance selon le rôle ----------

def test_performance_defaults_to_own_figures_for_sdr(temp_db):
    ids = _team_with_prospects()
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    menu = next(s for s in at.sidebar.selectbox if s.label == "Signed in as")

    menu.select(ids["Léa Martin"]).run()
    at.sidebar.radio[0].set_value("Performance").run()
    assert not at.exception
    assert at.multiselect(key="performance_owners").value == ["Léa Martin"]
    assert any("shown to managers" in c.value for c in at.caption)

    menu = next(s for s in at.sidebar.selectbox if s.label == "Signed in as")   # élément de la page actuelle
    menu.select(ids["Nina Roy"]).run()                                   # un manager : toute l'équipe
    assert not at.exception
    assert at.multiselect(key="performance_owners").value == []
    assert any("By sales owner" in m.value for m in at.markdown)
