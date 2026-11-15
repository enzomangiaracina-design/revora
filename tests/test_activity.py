"""Tests de l'Activity Manager (base temporaire)."""

from datetime import date, datetime, timedelta

import pytest

import database
from core import activity_service as service

NOW = datetime(2026, 11, 14, 15, 30)


def make(**overrides):
    data = {
        "channel": "Call", "direction": "Outbound", "event_type": "No answer",
        "subject": "Premier appel", "content": "Messagerie", "outcome": "",
        "occurred_at": datetime(2026, 11, 14, 10, 0), "duration_minutes": 0,
        "follow_up_date": None,
    }
    data.update(overrides)
    return data


# ---------- Heures locales / UTC ----------

def test_local_time_round_trip(thomas):
    """Une heure locale saisie est relue à l'identique, quelle que soit la conversion UTC."""

    database.add_interaction(
        thomas, "Call", "Outbound", "Completed", "", "x", "", occurred_at="2026-11-14 10:15:00"
    )

    assert database.get_interactions(thomas)[0]["occurred_at_local"] == "2026-11-14 10:15:00"


def test_default_time_is_now(thomas):
    database.add_interaction(thomas, "Note", "Internal", "Other", "", "x", "")

    stored = datetime.fromisoformat(database.get_interactions(thomas)[0]["occurred_at_local"])
    assert abs(stored - datetime.now()) < timedelta(minutes=1)


def test_old_signature_still_works(thomas):
    """L'appel à 7 arguments (version 0.3) reste valide."""

    assert database.add_interaction(thomas, "Email", "Outbound", "Completed", "Objet", "Corps", "")
    assert database.get_interactions(thomas)[0]["metadata"] == {}


# ---------- Enregistrement via le service ----------

def test_log_call_with_duration(thomas):
    ok, _ = service.log_interaction(thomas, make(duration_minutes=5.5), now=NOW)

    item = database.get_interactions(thomas)[0]
    assert ok
    assert item["metadata"] == {"duration_seconds": 330}
    assert item["provider"] == "manual"
    assert service.format_duration(item["metadata"]) == "5 min 30 s"


def test_duration_ignored_for_emails(thomas):
    service.log_interaction(thomas, make(channel="Email", duration_minutes=3), now=NOW)

    assert database.get_interactions(thomas)[0]["metadata"] == {}


@pytest.mark.parametrize("overrides, expected", [
    ({"subject": "", "content": "  "}, "subject or a note"),
    ({"channel": "Fax"}, "Unknown"),
    ({"occurred_at": NOW + timedelta(hours=2)}, "futur"),
    ({"follow_up_date": date(2026, 11, 13)}, "must be after"),
])
def test_log_rejects_invalid(thomas, overrides, expected):
    ok, message = service.log_interaction(thomas, make(**overrides), now=NOW)

    assert not ok
    assert expected in message
    assert database.get_interactions(thomas) == []
    assert database.get_tasks(thomas) == []


def test_log_with_follow_up_creates_task(thomas):
    ok, message = service.log_interaction(
        thomas, make(outcome="Rappeler mardi", follow_up_date=date(2026, 11, 17)), now=NOW
    )

    task = database.get_tasks(thomas)[0]
    assert ok and "follow-up" in message
    assert task["title"] == "Rappeler mardi"
    assert task["due_at"] == "2026-11-17"


def test_follow_up_without_next_step_gets_default_title(thomas):
    service.log_interaction(thomas, make(follow_up_date=date(2026, 11, 20)), now=NOW)

    assert database.get_tasks(thomas)[0]["title"] == "Follow up after call"


# ---------- Vues globales et compteurs ----------

def test_all_interactions_filters(thomas):
    database.create_prospect("Julie", "Durand", "BankCo", "Finance", "j@bank.fr", None, None)
    julie = [p for p in database.get_all_prospects() if p["first_name"] == "Julie"][0]["id"]

    database.add_interaction(thomas, "Call", "Outbound", "Completed", "", "a", "", occurred_at="2026-11-01 09:00:00")
    database.add_interaction(thomas, "Email", "Outbound", "Completed", "", "b", "", occurred_at="2026-11-10 09:00:00")
    database.add_interaction(julie, "Call", "Inbound", "Completed", "", "c", "", occurred_at="2026-11-14 09:00:00")

    everything = database.get_all_interactions()
    assert [i["content"] for i in everything] == ["c", "b", "a"]  # plus récent d'abord
    assert everything[0]["company_name"] == "BankCo"

    assert [i["content"] for i in database.get_all_interactions(channels=["Call"])] == ["c", "a"]
    assert [i["content"] for i in database.get_all_interactions(
        start_date="2026-11-10", end_date="2026-11-14")] == ["c", "b"]


def test_activity_summary(thomas):
    database.add_interaction(thomas, "Call", "Outbound", "Completed", "", "a", "", occurred_at="2026-11-01 09:00:00")
    database.add_interaction(thomas, "Call", "Outbound", "Completed", "", "b", "", occurred_at="2026-11-12 16:45:00")
    database.add_interaction(thomas, "Email", "Outbound", "Completed", "", "c", "", occurred_at="2026-11-05 09:00:00")
    database.create_task(thomas, "Plus tard", "", "2026-11-30")
    database.create_task(thomas, "Bientôt", "", "2026-11-18")
    database.create_task(thomas, "Déjà faite", "", "2026-11-10")
    database.complete_task([t for t in database.get_tasks(thomas) if t["title"] == "Déjà faite"][0]["id"])

    summary = database.get_activity_summary()[thomas]

    assert summary["calls"] == 2
    assert summary["emails"] == 1
    assert summary["notes"] == 0
    assert summary["last_interaction_at"] == "2026-11-12 16:45:00"
    assert summary["next_task_title"] == "Bientôt"  # la relance terminée est ignorée


def test_summary_for_prospect_without_activity(thomas):
    summary = database.get_activity_summary()[thomas]

    assert summary["calls"] == 0
    assert summary["last_interaction_at"] is None
    assert summary["next_task_title"] is None


def test_all_tasks_include_prospect(thomas):
    database.create_task(thomas, "Rappeler", "", "2026-11-18")

    task = database.get_all_tasks()[0]
    assert task["first_name"] == "Thomas"
    assert task["company_name"] == "AlphaEngine"


def test_group_tasks():
    tasks = [
        {"id": 1, "status": "A faire", "due_at": "2026-11-13"},
        {"id": 2, "status": "A faire", "due_at": "2026-11-14"},
        {"id": 3, "status": "A faire", "due_at": "2026-11-20"},
        {"id": 4, "status": "A faire", "due_at": None},
        {"id": 5, "status": "Terminee", "due_at": "2026-11-01"},
    ]

    groups = service.group_tasks(tasks, today=date(2026, 11, 14))

    assert {key: [t["id"] for t in value] for key, value in groups.items()} == {
        "overdue": [1], "today": [2], "upcoming": [3], "no_date": [4], "done": [5],
    }


@pytest.mark.parametrize("period, expected", [
    ("Today", ("2026-11-14", "2026-11-14")),
    ("Last 7 days", ("2026-11-08", "2026-11-14")),
    ("Last 30 days", ("2026-10-16", "2026-11-14")),
    ("All time", (None, None)),
])
def test_period_bounds(period, expected):
    assert service.period_bounds(period, today=date(2026, 11, 14)) == expected


def test_count_by_channel():
    counts = service.count_by_channel([{"channel": "Call"}, {"channel": "Call"}, {"channel": "Note"}])
    assert counts == {"Call": 2, "Email": 0, "LinkedIn": 0, "Note": 1}


@pytest.mark.parametrize("metadata, expected", [
    ({"duration_seconds": 300}, "5 min"),
    ({"duration_seconds": 65}, "1 min 5 s"),
    ({}, ""),
    (None, ""),
])
def test_format_duration(metadata, expected):
    assert service.format_duration(metadata) == expected


# ---------- P2.2 : source des interactions et état des synchronisations ----------

from core.activity_service import filter_by_source, source_label, source_options, sync_status


def test_source_label_and_options():
    items = [{"provider": "manual"}, {"provider": None}, {"provider": "gmail"}, {"provider": "noota"}]

    assert [source_label(i["provider"]) for i in items] == ["Manual", "Manual", "Gmail", "Noota"]
    assert source_options(items) == ["Manual", "HubSpot", "Gmail", "Noota"]


def test_filter_by_source():
    items = [{"provider": "manual"}, {"provider": "hubspot"}, {"provider": "gmail"}]

    assert filter_by_source(items, ["HubSpot", "Gmail"]) == items[1:]
    assert filter_by_source(items, []) == items


def test_sync_status_reports_only_what_is_recorded():
    lines = sync_status({
        "hubspot": {"status": "Connected", "last_sync_at": "2026-11-15 13:04:00", "last_error": None},
        "gmail": {"status": "Error", "last_sync_at": None, "last_error": "HTTP 401"},
    })

    assert lines == [
        {"label": "HubSpot", "state": "connected", "text": "last sync 15/11 13:04"},
        {"label": "Gmail", "state": "error", "text": "error: HTTP 401 (never synced)"},
    ]
    assert [l["state"] for l in sync_status({})] == ["not_connected", "not_connected"]


def test_sync_status_from_database(temp_db):
    database.set_integration_status("gmail", "Error", "Token expired")

    gmail = sync_status(database.get_integrations())[1]
    assert (gmail["state"], gmail["text"]) == ("error", "error: Token expired (never synced)")


# ---------- Correction et suppression d'une interaction ----------

def test_edit_interaction_applies_the_same_rules(thomas):
    service.log_interaction(thomas, make(), now=NOW)
    interaction_id = database.get_interactions(thomas)[0]["id"]

    ok, _ = service.edit_interaction(
        interaction_id, make(event_type="Completed", subject="Appel corrigé", duration_minutes=4,
                             occurred_at=datetime(2026, 11, 13, 16, 30)), now=NOW)

    saved = database.get_interaction(interaction_id)
    assert ok
    assert (saved["event_type"], saved["subject"], saved["occurred_at_local"]) == (
        "Completed", "Appel corrigé", "2026-11-13 16:30:00")
    assert saved["metadata"] == {"duration_seconds": 240}

    ok, message = service.edit_interaction(interaction_id, make(subject="", content=""), now=NOW)
    assert not ok and message == "Enter a subject or a note."
    assert database.get_interaction(interaction_id)["subject"] == "Appel corrigé"   # inchangée


def test_synced_interaction_cannot_be_edited_or_deleted(thomas):
    database.add_external_interaction(thomas, "gmail", "m-1", "Email", "Inbound", "Completed",
                                      "2026-11-14 09:00:00", subject="Re: offre")
    interaction_id = database.get_interactions(thomas)[0]["id"]

    assert service.edit_interaction(interaction_id, make(), now=NOW)[0] is False
    ok, message = service.remove_interaction(interaction_id)
    assert not ok and "Gmail" in message
    assert database.get_interaction(interaction_id) is not None


def test_delete_interaction_keeps_its_objections(thomas):
    service.log_interaction(thomas, make(objection_category="No budget"), now=NOW)
    interaction_id = database.get_interactions(thomas)[0]["id"]

    ok, message = service.remove_interaction(interaction_id)

    assert ok and "1 objection(s) kept" in message
    assert database.get_interactions(thomas) == []
    objection = database.get_objections(thomas)[0]
    assert (objection["category"], objection["interaction_id"]) == ("No budget", None)


def test_unknown_interaction(thomas):
    assert service.remove_interaction(9999) == (False, "Interaction not found.")
    assert service.edit_interaction(9999, make()) == (False, "Interaction not found.")
