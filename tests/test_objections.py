"""Tests de l'Objection Intelligence (base temporaire)."""

from datetime import date, datetime

import pytest

import database
from core import activity_service
from core import objection_service as service

TODAY = date(2026, 11, 14)


def objection(category, day="2026-11-10", status="Open", verbatim=None, **extra):
    return {"category": category, "occurred_at_local": f"{day} 10:00:00", "status": status,
            "verbatim": verbatim, **extra}


# ---------- Enregistrement ----------

def test_record_objection_keeps_stage_at_that_time(thomas):
    database.set_prospect_stage(thomas, "En contact")

    ok, _ = service.record_objection(thomas, " No budget ", "Pas de budget avant mars")
    database.set_prospect_stage(thomas, "Intéressé")

    saved = database.get_objections(thomas)[0]
    assert ok
    assert (saved["category"], saved["stage"], saved["status"], saved["source"]) == (
        "No budget", "En contact", "Open", "manual")
    assert saved["verbatim"] == "Pas de budget avant mars"
    assert saved["company_name"] == "AlphaEngine"


def test_record_objection_requires_category(thomas):
    ok, message = service.record_objection(thomas, "  ")

    assert not ok and "catégorie" in message
    assert database.get_objections() == []


def test_local_time_round_trip(thomas):
    service.record_objection(thomas, "Bad timing", occurred_at=datetime(2026, 11, 3, 16, 45))

    assert database.get_objections(thomas)[0]["occurred_at_local"] == "2026-11-03 16:45:00"


def test_objection_logged_with_interaction(thomas):
    ok, message = activity_service.log_interaction(thomas, {
        "channel": "Call", "direction": "Outbound", "event_type": "Objection",
        "subject": "Appel", "content": "Pas le bon moment", "outcome": "",
        "occurred_at": datetime(2026, 11, 14, 9, 0), "duration_minutes": 0,
        "follow_up_date": None, "objection_category": "Bad timing",
        "objection_verbatim": "Rappelez-moi en janvier",
    }, now=datetime(2026, 11, 14, 12, 0))

    interaction = database.get_interactions(thomas)[0]
    saved = database.get_objections(thomas)[0]

    assert ok and "Bad timing" in message
    assert saved["interaction_id"] == interaction["id"]
    assert saved["occurred_at_local"] == "2026-11-14 09:00:00"


def test_interaction_without_objection_creates_none(thomas):
    activity_service.log_interaction(thomas, {
        "channel": "Email", "direction": "Outbound", "event_type": "Completed",
        "subject": "Bonjour", "content": "", "occurred_at": datetime(2026, 11, 14, 9, 0),
        "objection_category": None,
    }, now=datetime(2026, 11, 14, 12, 0))

    assert database.get_objections() == []


def test_status_and_delete(thomas):
    service.record_objection(thomas, "Price too high")
    objection_id = database.get_objections()[0]["id"]

    database.set_objection_status(objection_id, "Handled")
    assert database.get_objections()[0]["status"] == "Handled"

    database.delete_objection(objection_id)
    assert database.get_objections() == []


def test_playbook_responses(temp_db):
    database.set_objection_response("No budget", "Proposer un pilote")
    database.set_objection_response("No budget", "Proposer un pilote de 30 jours")
    database.set_objection_response("Bad timing", "Fixer une date")

    assert database.get_objection_responses() == {
        "No budget": "Proposer un pilote de 30 jours", "Bad timing": "Fixer une date",
    }

    database.set_objection_response("Bad timing", "   ")  # vide = suppression
    assert "Bad timing" not in database.get_objection_responses()


# ---------- Statistiques ----------

SAMPLE = [
    objection("No budget", "2026-11-13", "Handled", vertical="SaaS", stage="En contact"),
    objection("No budget", "2026-11-03", "Open", vertical="Finance", stage="Intéressé"),
    objection("Bad timing", "2026-11-12", "Lost", vertical="SaaS", stage="En contact"),
    objection("Competitor solution", "2026-08-01", "Open", vertical=None, stage="En contact"),
]


def test_categories_include_new_ones():
    cats = service.categories([objection("Contrat en cours")])

    assert cats[:len(service.DEFAULT_CATEGORIES)] == service.DEFAULT_CATEGORIES
    assert cats[-1] == "Contrat en cours"


def test_count_by():
    assert service.count_by(SAMPLE, "category") == [
        ("No budget", 2), ("Bad timing", 1), ("Competitor solution", 1),
    ]
    assert service.count_by(SAMPLE, "vertical") == [("SaaS", 2), ("Finance", 1), ("Unknown", 1)]


def test_filter_period():
    assert len(service.filter_period(SAMPLE, 30, TODAY)) == 3
    assert len(service.filter_period(SAMPLE, None, TODAY)) == 4


def test_weekly_trend():
    assert service.week_start("2026-11-14") == "2026-11-09"  # lundi
    assert service.weekly_trend(SAMPLE) == {
        "2026-07-27": {"Competitor solution": 1},
        "2026-11-02": {"No budget": 1},
        "2026-11-09": {"No budget": 1, "Bad timing": 1},
    }


def test_resolution_by_category():
    rows = {r["Category"]: r for r in service.resolution_by_category(SAMPLE)}

    assert rows["No budget"] == {"Category": "No budget", "Total": 2, "Handled": 1, "Lost": 0,
                                 "Open": 1, "Handled rate (%)": 50}
    assert rows["Bad timing"]["Lost"] == 1


# ---------- Anonymisation ----------

PERSON = {"first_name": "Thomas", "last_name": "Martins", "company_name": "AlphaEngine"}


@pytest.mark.parametrize("text, expected", [
    ("Thomas Martins dit que AlphaEngine n'a pas de budget",
     "[contact] dit que [company] n'a pas de budget"),
    ("Écrivez à thomas.martin@example.com ou au 06 12 34 56 78",
     "Écrivez à [email] ou au [phone]"),
    ("Voir https://alphaengine.example/pricing", "Voir [link]"),
    ("ALPHAENGINE a déjà un outil", "[company] a déjà un outil"),
    ("Thomasine n'est pas concernée", "Thomasine n'est pas concernée"),  # mot différent conservé
    ("Budget gelé jusqu'en 2027", "Budget gelé jusqu'en 2027"),          # année non prise pour un téléphone
])
def test_anonymize(text, expected):
    assert service.anonymize(text, PERSON) == expected


def test_anonymized_examples_are_distinct_and_limited():
    items = [
        objection("No budget", verbatim="Thomas: pas de budget", **PERSON),
        objection("No budget", verbatim="Thomas : pas de budget", **PERSON),
        objection("No budget", verbatim="Thomas: pas de budget", **PERSON),
        objection("Bad timing", verbatim="Trop tôt", **PERSON),
        objection("No budget", verbatim=None, **PERSON),
    ]

    examples = service.anonymized_examples(items, "No budget", limit=5)

    assert examples == ["[contact]: pas de budget", "[contact] : pas de budget"]
    assert service.anonymized_examples(items, "No budget", limit=1) == ["[contact]: pas de budget"]


# ---------- Préparation d'appel ----------

def test_call_preparation(thomas):
    service.record_objection(thomas, "Bad timing", "Rappelez en janvier", occurred_at=datetime(2026, 11, 1, 9))
    service.record_objection(thomas, "No budget", "Budget gelé", occurred_at=datetime(2026, 11, 5, 9))
    service.record_objection(thomas, "No budget", occurred_at=datetime(2026, 11, 10, 9))
    database.set_objection_status(database.get_objections()[-1]["id"], "Handled")  # Bad timing traitée
    database.set_objection_response("No budget", "Proposer un pilote")

    prep = service.call_preparation(thomas)

    assert [p["category"] for p in prep] == ["No budget", "Bad timing"]  # ouvertes d'abord
    assert prep[0] == {"category": "No budget", "count": 2, "open": 2, "last_seen": "2026-11-10",
                       "verbatims": ["Budget gelé"], "response": "Proposer un pilote"}
    assert (prep[1]["open"], prep[1]["response"]) == (0, None)


def test_date_cannot_be_passed_as_interaction_id(thomas):
    """Garde-fou : interaction_id et occurred_at doivent être nommés."""

    with pytest.raises(TypeError):
        service.record_objection(thomas, "No budget", "x", datetime(2026, 11, 3, 10))

    assert database.get_objections() == []
