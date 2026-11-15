"""Tests de l'Overview (cockpit) : en-tête, focus du jour, fil d'activité."""

from datetime import date, datetime

import pytest

import database
from core import overview_service as overview
from core import score_service

TODAY = date(2026, 11, 15)


@pytest.mark.parametrize("hour, expected", [
    (8, "Good morning."), (12, "Good afternoon."), (17, "Good afternoon."), (18, "Good evening."),
])
def test_greeting(hour, expected):
    assert overview.greeting(datetime(2026, 11, 15, hour, 0)) == expected


def test_long_date():
    assert overview.long_date(TODAY) == "Sunday 15 November 2026"


@pytest.mark.parametrize("points, label", [(5, "High"), (3, "High"), (2, "Medium"), (1, "Low")])
def test_priority_label(points, label):
    assert overview.priority_label(points) == label


def item(summary=None, **prospect):
    return {"prospect": {"id": 1, **prospect}, "summary": summary or {}, "points": 1, "reasons": []}


OVERDUE = {"next_task_title": "Envoyer la proposition", "next_task_due": "2026-11-12",
           "next_task_created_at": "2026-11-10 09:00:00", "next_task_id": 7,
           "last_interaction_at": "2026-11-10 10:00:00", "last_channel": "Call"}


@pytest.mark.parametrize("summary, prospect, expected", [
    (OVERDUE, {}, "Follow up"),
    ({}, {"phone": "0611", "email": "a@b.c"}, "Call"),
    ({}, {"email": "a@b.c"}, "Email"),
    ({}, {}, "Prepare"),
    ({"last_interaction_at": "2026-10-26 09:00:00", "last_channel": "LinkedIn"}, {"phone": "0611"}, "LinkedIn"),
    ({"last_interaction_at": "2026-10-26 09:00:00", "last_channel": "Note"}, {"email": "a@b.c"}, "Email"),
])
def test_action_type(summary, prospect, expected):
    assert overview.action_type(item(summary, **prospect), TODAY) == expected


@pytest.mark.parametrize("summary, prospect, expected", [
    (OVERDUE, {}, "Follow-up: Envoyer la proposition"),
    ({"next_task_title": "Démo", "next_task_due": "2026-11-15"}, {}, "Follow-up: Démo"),
    ({}, {"phone": "0611"}, "First contact: call"),
    ({}, {"email": "a@b.c"}, "First contact: email"),
    ({}, {}, "Prepare: find a phone number or an email"),
    ({"next_task_title": "Plus tard", "next_task_due": "2026-11-30",
      "last_interaction_at": "2026-10-26 09:00:00", "last_channel": "Email"}, {}, "Re-engage by email: no touch for 20 days"),
])
def test_next_action_follows_the_reason(summary, prospect, expected):
    assert overview.next_action(item(summary, **prospect), TODAY) == expected


@pytest.mark.parametrize("summary, expected", [
    (OVERDUE, ("Overdue 3 d", "overdue")),
    ({"next_task_title": "Démo", "next_task_due": "2026-11-15"}, ("Today", "today")),
    ({"next_task_title": "Plus tard", "next_task_due": "2026-11-30"}, ("Due 30/11", "later")),
    ({}, ("—", "none")),
])
def test_due_label(summary, expected):
    assert overview.due_label(item(summary), TODAY) == expected


@pytest.mark.parametrize("summary, prospect, expected", [
    (OVERDUE, {}, "Follow-up due 12/11 (scheduled 10/11)"),
    ({}, {"created_at_local": "2026-11-01 09:00:00", "source": "Import CSV"},
     "Never contacted · added 01/11 via Import CSV"),
    ({"next_task_title": "Démo", "next_task_due": "2026-11-15"}, {"created_at_local": "2026-11-14 09:00:00"},
     "Follow-up due 15/11 · Never contacted · added 14/11"),
    ({"last_interaction_at": "2026-10-21 10:19:00", "last_channel": "Call"}, {},
     "No touch for 25 d · last call on 21/10"),
])
def test_reason_detail_gives_source_and_date(summary, prospect, expected):
    assert overview.reason_detail(item(summary, **prospect), TODAY) == expected


def test_focus_rows():
    ranked = [
        {"prospect": {"id": 1, "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta",
                      "status": "In contact", "phone": "0611"},
         "points": 3, "reasons": ["Overdue follow-up (2026-11-12): Rappel"],
         "summary": {"next_task_title": "Rappel", "next_task_due": "2026-11-12", "next_task_id": 4,
                     "next_task_created_at": "2026-11-09 08:00:00",
                     "last_interaction_at": "2026-11-14 16:20:00", "last_channel": "Call"}},
        {"prospect": {"id": 2, "first_name": "Bob", "last_name": "Ray", "company_name": None,
                      "status": "To prospect"},
         "points": 1, "reasons": ["Never contacted"], "summary": {}},
    ]

    rows = overview.focus_rows(ranked, {1: {"global": 56, "temperature": "Warm"}}, limit=5, today=TODAY)

    assert rows[0] == {
        "id": 1, "priority": "High", "prospect": "Ana Lopez", "company": "Zeta", "stage": "In contact",
        "score": 56, "temperature": "Warm", "last_interaction": "Yesterday 16:20",
        "action_type": "Follow up", "next_action": "Follow-up: Rappel",
        "due": "Overdue 3 d", "due_state": "overdue",
        "reason": "Follow-up due 12/11 (scheduled 09/11)", "task_id": 4, "task_title": "Rappel",
    }
    assert (rows[1]["company"], rows[1]["score"], rows[1]["last_interaction"]) == ("—", None, "Never")
    assert (rows[1]["action_type"], rows[1]["due"], rows[1]["task_id"]) == ("Prepare", "—", None)
    assert len(overview.focus_rows(ranked, {}, limit=1, today=TODAY)) == 1


@pytest.mark.parametrize("value, expected", [
    ("2026-11-15 14:32:00", "14:32"),
    ("2026-11-14 10:40:00", "Yesterday 10:40"),
    ("2026-11-12 09:05:00", "12/11 09:05"),
    (None, None),
])
def test_format_when(value, expected):
    assert overview.format_when(value, TODAY) == expected


def test_build_feed_merges_and_sorts():
    interactions = [{"occurred_at_local": "2026-11-15 14:32:00", "channel": "Call", "direction": "Outbound",
                     "event_type": "No answer", "subject": "", "contact_id": 1,
                     "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta"}]
    objections = [{"occurred_at_local": "2026-11-15 10:00:00", "category": "No budget", "verbatim": "x",
                   "contact_id": 1, "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta"}]
    prospects = [{"id": 1, "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta",
                  "created_at_local": "2026-11-01 09:00:00", "source": "Import CSV"}]
    changes = [{"contact_id": 1, "occurred_at_local": "2026-11-15 12:00:00", "global_score": 56,
                "previous_score": 34},
               {"contact_id": 99, "occurred_at_local": "2026-11-15 13:00:00", "global_score": 10,
                "previous_score": 50}]  # prospect supprimé : ignoré

    feed = overview.build_feed(interactions, objections, prospects, changes, limit=10)

    assert [e["title"] for e in feed] == [
        "Call out · No answer", "Score 34 → 56", "Objection · No budget", "New prospect",
    ]
    assert {e["contact_id"] for e in feed} == {1}
    assert feed[0]["prospect"] == "Ana Lopez" and feed[0]["company"] == "Zeta"
    assert len(overview.build_feed(interactions, objections, prospects, changes, limit=2)) == 2


def test_recent_score_changes(thomas):
    score_service.refresh_scores(TODAY)                                   # premier score : pas une variation
    database.update_qualification(thomas, {"budget_confirmed": True})    # +30 en Intent
    score_service.refresh_scores(TODAY)

    changes = database.get_recent_score_changes()
    assert len(changes) == 1
    assert changes[0]["contact_id"] == thomas
    assert changes[0]["global_score"] > changes[0]["previous_score"]

    # Petite variation (< 5 points) ignorée par défaut
    assert database.get_recent_score_changes(min_change=1000) == []
