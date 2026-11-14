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
    assert {s["name"] for s in stages if s["is_closed"]} == {"Non intéressé", "Disqualifié"}


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
    assert not ok and "existe" in message

    ok, _ = database.add_stage("   ")
    assert not ok


def test_rename_stage_updates_prospects(thomas):
    ok, _ = database.rename_stage(stage_id("A prospecter"), "Nouveau lead")

    assert ok
    assert database.get_stage_names()[0] == "Nouveau lead"
    assert database.get_prospect_by_id(thomas)["status"] == "Nouveau lead"


def test_rename_stage_refuses_existing_name(thomas):
    ok, _ = database.rename_stage(stage_id("A prospecter"), "en contact")

    assert not ok
    assert database.get_prospect_by_id(thomas)["status"] == "A prospecter"


def test_move_stage(temp_db):
    assert database.move_stage(stage_id("En contact"), -1)
    assert database.get_stage_names()[1:3] == ["En contact", "Première tentative"]

    # La première étape ne peut pas aller plus à gauche
    assert not database.move_stage(stage_id("A prospecter"), -1)


def test_set_stage_closed(temp_db):
    database.set_stage_closed(stage_id("A relancer"), True)

    assert next(s for s in database.get_stages() if s["name"] == "A relancer")["is_closed"]


def test_delete_empty_stage(temp_db):
    ok, _ = database.delete_stage(stage_id("A relancer"))

    assert ok
    assert "A relancer" not in database.get_stage_names()


def test_delete_stage_with_prospects_requires_target(thomas):
    ok, message = database.delete_stage(stage_id("A prospecter"))

    assert not ok and "destination" in message
    assert "A prospecter" in database.get_stage_names()

    ok, _ = database.delete_stage(stage_id("A prospecter"), move_to="En contact")

    assert ok
    assert database.get_prospect_by_id(thomas)["status"] == "En contact"


def test_cannot_delete_last_stage(temp_db):
    for name in database.DEFAULT_STAGES[1:]:
        database.delete_stage(stage_id(name))

    ok, message = database.delete_stage(stage_id("A prospecter"))

    assert not ok and "au moins une" in message


def test_set_prospect_stage(thomas):
    ok, _ = database.set_prospect_stage(thomas, "Intéressé")
    assert ok
    assert database.get_prospect_by_id(thomas)["status"] == "Intéressé"

    ok, _ = database.set_prospect_stage(thomas, "Inventée")
    assert not ok
    assert database.get_prospect_by_id(thomas)["status"] == "Intéressé"


# ---------- Statuts dynamiques dans le service prospects ----------

def test_custom_stage_accepted_and_first_stage_is_default(temp_db):
    database.rename_stage(stage_id("A prospecter"), "Lead")
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
    {"name": "A prospecter", "is_closed": False},
    {"name": "En contact", "is_closed": False},
    {"name": "Intéressé", "is_closed": False},
    {"name": "Disqualifié", "is_closed": True},
]


def p(pid, status):
    return {"id": pid, "first_name": f"P{pid}", "last_name": "X", "status": status}


def test_build_board():
    board = pipeline.build_board([p(1, "En contact"), p(2, "Inconnu"), p(3, "En contact")], STAGES)

    assert [x["id"] for x in board["En contact"]] == [1, 3]
    assert [x["id"] for x in board["A prospecter"]] == [2]  # statut inconnu : pas masqué
    assert board["Disqualifié"] == []


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
    prospects = [p(1, "A prospecter"), p(2, "Intéressé"), p(3, "En contact"),
                 p(4, "Disqualifié"), p(5, "En contact"), p(6, "Intéressé")]
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
