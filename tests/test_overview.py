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


@pytest.mark.parametrize("summary, expected", [
    ({"next_task_title": "Envoyer la proposition", "next_task_due": "2026-11-12",
      "last_interaction_at": "2026-11-10 09:00:00"}, "Follow-up: Envoyer la proposition"),
    ({"next_task_title": "Démo", "next_task_due": "2026-11-15"}, "Follow-up: Démo"),
    ({}, "First contact: call or email"),
    ({"next_task_title": "Plus tard", "next_task_due": "2026-11-30",
      "last_interaction_at": "2026-10-26 09:00:00"}, "Re-engage: no touch for 20 days"),
])
def test_next_action_follows_the_reason(summary, expected):
    assert overview.next_action({"summary": summary}, TODAY) == expected


def test_focus_rows():
    ranked = [
        {"prospect": {"id": 1, "first_name": "Ana", "last_name": "Lopez", "company_name": "Zeta",
                      "status": "En contact"},
         "points": 3, "reasons": ["Overdue follow-up (2026-11-12): Rappel"],
         "summary": {"next_task_title": "Rappel", "next_task_due": "2026-11-12",
                     "last_interaction_at": "2026-11-14 16:20:00"}},
        {"prospect": {"id": 2, "first_name": "Bob", "last_name": "Ray", "company_name": None,
                      "status": "A prospecter"},
         "points": 1, "reasons": ["Never contacted"], "summary": {}},
    ]

    rows = overview.focus_rows(ranked, {1: {"global": 56, "temperature": "Warm"}}, limit=5, today=TODAY)

    assert rows[0] == {
        "id": 1, "priority": "High", "prospect": "Ana Lopez", "company": "Zeta", "stage": "En contact",
        "score": 56, "temperature": "Warm", "last_interaction": "Yesterday 16:20",
        "next_action": "Follow-up: Rappel", "reason": "Overdue follow-up (2026-11-12): Rappel",
    }
    assert (rows[1]["company"], rows[1]["score"], rows[1]["last_interaction"]) == ("—", None, "Never")
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
