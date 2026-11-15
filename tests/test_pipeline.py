"""Tests du pipeline : étapes personnalisables, tableau, inactivité, priorités."""

import sqlite3
from datetime import date

import pytest

import database
from core import pipeline_service as pipeline
from core import prospect_service

TODAY = date(2026, 11, 14)


def stage_id(name):
    return next(s["id"] for s in database.get_stages() if s["name"] == name)


# ---------- Étapes (base de données) ----------

def test_default_stages_are_seeded(temp_db):
    stages = database.get_stages()

    assert [s["name"] for s in stages] == database.DEFAULT_STAGES
    assert {s["name"] for s in stages if s["is_closed"]} == {"Not interested", "Disqualified"}


def test_seeding_is_idempotent(thomas):
    database.initialize_database()

    assert database.get_stage_names() == database.DEFAULT_STAGES


def test_unknown_existing_status_becomes_a_stage(tmp_path, monkeypatch):
    """Un statut déjà utilisé mais absent des étapes par défaut n'est pas perdu."""

    path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    database.initialize_database()

    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE pipeline_stages")
    connection.execute("INSERT INTO companies (name) VALUES ('X')")
    connection.execute(
        "INSERT INTO contacts (company_id, first_name, last_name, status) VALUES (1, 'A', 'B', 'Statut maison')"
    )
    connection.commit()
    connection.close()

    database.initialize_database()

    assert database.get_stage_names()[-1] == "Statut maison"


def test_add_stage(temp_db):
    ok, _ = database.add_stage("Démo planifiée")
    assert ok
    assert database.get_stage_names()[-1] == "Démo planifiée"

    ok, message = database.add_stage("démo PLANIFIÉE ")
    assert not ok and "already exists" in message

    ok, _ = database.add_stage("   ")
    assert not ok


def test_rename_stage_updates_prospects(thomas):
    ok, _ = database.rename_stage(stage_id("To prospect"), "Nouveau lead")

    assert ok
    assert database.get_stage_names()[0] == "Nouveau lead"
    assert database.get_prospect_by_id(thomas)["status"] == "Nouveau lead"


def test_rename_stage_refuses_existing_name(thomas):
    ok, _ = database.rename_stage(stage_id("To prospect"), "in CONTACT")

    assert not ok
    assert database.get_prospect_by_id(thomas)["status"] == "To prospect"


def test_move_stage(temp_db):
    assert database.move_stage(stage_id("In contact"), -1)
    assert database.get_stage_names()[1:3] == ["In contact", "First attempt"]

    # La première étape ne peut pas aller plus à gauche
    assert not database.move_stage(stage_id("To prospect"), -1)


def test_set_stage_closed(temp_db):
    database.set_stage_closed(stage_id("To follow up"), True)

    assert next(s for s in database.get_stages() if s["name"] == "To follow up")["is_closed"]


def test_delete_empty_stage(temp_db):
    ok, _ = database.delete_stage(stage_id("To follow up"))

    assert ok
    assert "To follow up" not in database.get_stage_names()


def test_delete_stage_with_prospects_requires_target(thomas):
    ok, message = database.delete_stage(stage_id("To prospect"))

    assert not ok and "destination" in message
    assert "To prospect" in database.get_stage_names()

    ok, _ = database.delete_stage(stage_id("To prospect"), move_to="In contact")

    assert ok
    assert database.get_prospect_by_id(thomas)["status"] == "In contact"


def test_cannot_delete_last_stage(temp_db):
    for name in database.DEFAULT_STAGES[1:]:
        database.delete_stage(stage_id(name))

    ok, message = database.delete_stage(stage_id("To prospect"))

    assert not ok and "at least one" in message


def test_set_prospect_stage(thomas):
    ok, _ = database.set_prospect_stage(thomas, "Interested")
    assert ok
    assert database.get_prospect_by_id(thomas)["status"] == "Interested"

    ok, _ = database.set_prospect_stage(thomas, "Inventée")
    assert not ok
    assert database.get_prospect_by_id(thomas)["status"] == "Interested"


# ---------- Statuts dynamiques dans le service prospects ----------

def test_custom_stage_accepted_and_first_stage_is_default(temp_db):
    database.rename_stage(stage_id("To prospect"), "Lead")
    database.add_stage("Démo")

    ok, _ = prospect_service.create_prospect({
        "first_name": "Ana", "last_name": "Lopez", "company_name": "Acme", "status": "",
    })
    assert ok
    assert database.get_all_prospects()[0]["status"] == "Lead"

    ok, _ = prospect_service.create_prospect({
        "first_name": "Bob", "last_name": "Ray", "company_name": "Acme", "status": "Démo",
    })
    assert ok


def test_filter_by_owner():
    prospects = [{"id": 1, "owner": "Enzo"}, {"id": 2, "owner": "Léa"}, {"id": 3, "owner": None}]

    assert [p["id"] for p in prospect_service.filter_prospects(prospects, owners=["Léa"])] == [2]


# ---------- Tableau, inactivité, priorités (fonctions pures) ----------

STAGES = [
    {"name": "To prospect", "is_closed": False},
    {"name": "In contact", "is_closed": False},
    {"name": "Interested", "is_closed": False},
    {"name": "Disqualified", "is_closed": True},
]


def p(pid, status):
    return {"id": pid, "first_name": f"P{pid}", "last_name": "X", "status": status}


def test_build_board():
    board = pipeline.build_board([p(1, "In contact"), p(2, "Inconnu"), p(3, "In contact")], STAGES)

    assert [x["id"] for x in board["In contact"]] == [1, 3]
    assert [x["id"] for x in board["To prospect"]] == [2]  # statut inconnu : pas masqué
    assert board["Disqualified"] == []


@pytest.mark.parametrize("last, expected", [
    (None, None),
    ("2026-11-14 09:00:00", 0),
    ("2026-11-01 23:59:00", 13),
])
def test_days_since(last, expected):
    assert pipeline.days_since(last, TODAY) == expected


def test_is_stale():
    assert pipeline.is_stale({}, 14, TODAY)  # jamais contacté
    assert pipeline.is_stale({"last_interaction_at": "2026-10-31 10:00:00"}, 14, TODAY)
    assert not pipeline.is_stale({"last_interaction_at": "2026-11-10 10:00:00"}, 14, TODAY)


def test_prioritize():
    prospects = [p(1, "To prospect"), p(2, "Interested"), p(3, "In contact"),
                 p(4, "Disqualified"), p(5, "In contact"), p(6, "Interested")]
    summaries = {
        1: {},                                                        # jamais contacté : 1
        2: {"last_interaction_at": "2026-11-13 10:00:00",
            "next_task_due": "2026-11-10", "next_task_title": "Rappel"},  # en retard : 3
        3: {"last_interaction_at": "2026-11-13 10:00:00",
            "next_task_due": "2026-11-14", "next_task_title": "Démo"},    # aujourd'hui : 2
        4: {},                                                        # étape fermée : exclu
        5: {"last_interaction_at": "2026-11-12 10:00:00"},            # récent, rien : exclu
        6: {"last_interaction_at": "2026-10-01 10:00:00"},            # inactif : 1
    }

    ranked = pipeline.prioritize(prospects, STAGES, summaries, stale_days=14, today=TODAY)

    assert [(r["prospect"]["id"], r["points"]) for r in ranked] == [(2, 3), (3, 2), (6, 1), (1, 1)]
    assert ranked[0]["reasons"] == ["Overdue follow-up (2026-11-10): Rappel"]
    assert ranked[2]["reasons"] == ["No activity for 44 days"]


def test_prioritize_ties_broken_by_score():
    prospects = [p(1, "To prospect"), p(2, "To prospect")]
    ranked = pipeline.prioritize(prospects, STAGES, {}, today=TODAY, scores={1: 20, 2: 65})

    assert [r["prospect"]["id"] for r in ranked] == [2, 1]


# ---------- Tableau façon HubSpot : cartes, tris, filtres rapides ----------

SUMMARIES = {
    1: {"last_interaction_at": "2026-11-13 10:00:00", "next_task_due": "2026-11-10", "next_task_title": "Relancer"},
    2: {"last_interaction_at": "2026-10-01 09:00:00", "next_task_due": "2026-11-14", "next_task_title": "Démo"},
    3: {},
}

PROSPECTS_HS = [
    {"id": 1, "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta", "owner": "Léa",
     "created_at": "2026-11-14 08:00:00", "created_at_local": "2026-11-14 09:00:00", "status": "To prospect"},
    {"id": 2, "first_name": "bob", "last_name": "ray", "company_name": "alpha", "owner": None,
     "created_at": "2026-10-20 08:00:00", "created_at_local": "2026-10-20 10:00:00", "status": "In contact"},
    {"id": 3, "first_name": "Chloé", "last_name": "", "company_name": None, "owner": "Léa",
     "created_at": "2026-11-10 08:00:00", "created_at_local": "2026-11-10 09:00:00", "status": "To prospect"},
]

SCORES = {1: {"global": 30, "temperature": "Cold"}, 2: {"global": 75, "temperature": "Hot"},
          3: {"global": 50, "temperature": "Warm"}}


def ids(items):
    return [p["id"] for p in items]


def test_format_date_and_initials():
    assert pipeline.format_date("2026-11-04 10:05:00") == "04/11/2026"
    assert pipeline.format_date(None) is None
    assert pipeline.initials("bob", "ray") == "BR"
    assert pipeline.initials("Chloé", "") == "C"
    assert pipeline.initials(None, None) == "?"


def test_build_card():
    card = pipeline.build_card(PROSPECTS_HS[0], SUMMARIES[1], SCORES[1], stale_days=14, today=TODAY)

    assert card == {
        "id": 1, "title": "Zeta", "contact": "Ana Lopez", "initials": "AL",
        "created": "14/11/2026", "last_activity": "13/11/2026 (1 d ago)", "stale": False,
        "next_follow_up": "10/11/2026 · Relancer", "overdue": True,
        "owner": "Léa", "score": 30, "temperature": "Cold",
    }

    empty = pipeline.build_card(PROSPECTS_HS[2], {}, None, today=TODAY)
    assert (empty["title"], empty["last_activity"], empty["stale"]) == ("No company", "Never contacted", True)
    assert (empty["next_follow_up"], empty["overdue"], empty["owner"]) == ("None scheduled", False, "Léa")
    assert (empty["score"], empty["temperature"]) == (0, "Cold")


@pytest.mark.parametrize("sort_by, expected", [
    ("Last activity (most recent)", [1, 2, 3]),
    ("Create date (newest)", [1, 3, 2]),
    ("Score (highest)", [2, 3, 1]),
    ("Next follow-up (soonest)", [1, 2, 3]),
    ("Company (A–Z)", [3, 2, 1]),  # sans entreprise d'abord, puis alpha, Zeta (sans tenir compte de la casse)
])
def test_sort_prospects(sort_by, expected):
    assert ids(pipeline.sort_prospects(PROSPECTS_HS, sort_by, SUMMARIES, SCORES)) == expected


@pytest.mark.parametrize("kwargs, expected", [
    ({}, [1, 2, 3]),
    ({"created": "Today"}, [1]),
    ({"created": "Last 7 days"}, [1, 3]),
    ({"activity": "Last 7 days"}, [1]),
    ({"activity": "Inactive"}, [2, 3]),
    ({"activity": "Never contacted"}, [3]),
    ({"follow_up": "Overdue"}, [1]),
    ({"follow_up": "Due today"}, [2]),
    ({"follow_up": "None scheduled"}, [3]),
    ({"created": "Last 30 days", "follow_up": "Due today"}, [2]),
])
def test_filter_quick(kwargs, expected):
    assert ids(pipeline.filter_quick(PROSPECTS_HS, SUMMARIES, stale_days=14, today=TODAY, **kwargs)) == expected


def test_created_at_local_is_returned(thomas):
    prospect = database.get_all_prospects()[0]
    assert prospect["created_at_local"]  # heure locale pour l'affichage et les filtres


# ---------- P2.4 : définition des étapes ----------

def test_stage_definition_is_saved_and_cleared(temp_db):
    stage = database.get_stages()[0]
    assert stage["definition"] is None

    database.set_stage_definition(stage["id"], "  Jamais contacté  ")
    assert database.get_stages()[0]["definition"] == "Jamais contacté"

    database.set_stage_definition(stage["id"], "  ")
    assert database.get_stages()[0]["definition"] is None
