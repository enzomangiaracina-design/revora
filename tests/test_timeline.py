"""Tests de P0.3 : historique des étapes et timeline unifiée de la fiche prospect."""

import database
from core import objection_service
from core.timeline_service import build_timeline, filter_timeline


def stage_id(name):
    return next(s["id"] for s in database.get_stages() if s["name"] == name)


# ---------- Historique des changements d'étape ----------

def test_pipeline_move_is_recorded(thomas):
    database.set_prospect_stage(thomas, "In contact")
    database.set_prospect_stage(thomas, "In contact")      # même étape : pas d'entrée
    database.set_prospect_stage(thomas, "Interested")

    changes = database.get_stage_changes(thomas)

    assert [(c["from_stage"], c["to_stage"], c["source"]) for c in changes] == [
        ("In contact", "Interested", "pipeline"),
        ("To prospect", "In contact", "pipeline"),
    ]
    assert changes[0]["changed_at_local"]


def test_unknown_stage_or_prospect_records_nothing(thomas):
    assert not database.set_prospect_stage(thomas, "Inventée")[0]
    assert not database.set_prospect_stage(9999, "In contact")[0]
    assert database.get_stage_changes(thomas) == []


def test_edit_form_change_is_recorded(thomas):
    database.update_prospect(thomas, "Thomas", "Martins", "AlphaEngine", "SaaS", None, None, None, "To follow up")
    database.update_prospect(thomas, "Thomas", "Martins", "AlphaEngine", "SaaS", None, None, "CEO", "To follow up")

    changes = database.get_stage_changes(thomas)
    assert [(c["from_stage"], c["to_stage"], c["source"]) for c in changes] == [
        ("To prospect", "To follow up", "edit"),
    ]


def test_deleting_a_stage_records_the_move(thomas):
    database.delete_stage(stage_id("To prospect"), move_to="In contact")

    change = database.get_stage_changes(thomas)[0]
    assert (change["from_stage"], change["to_stage"], change["source"]) == (
        "To prospect", "In contact", "stage deleted")


def test_history_is_deleted_with_the_prospect(thomas):
    database.set_prospect_stage(thomas, "In contact")
    deleted = database.delete_prospect(thomas)

    assert deleted["stage_changes"] == 1
    assert database.get_stage_changes(thomas) == []


# ---------- Timeline unifiée ----------

def test_build_timeline_merges_and_sorts():
    prospect = {"created_at_local": "2026-11-01 09:00:00", "source": "Import CSV"}
    interactions = [{"occurred_at_local": "2026-11-10 10:00:00", "channel": "Call", "direction": "Outbound",
                     "event_type": "Completed", "subject": "Discovery", "content": "Budget en mars",
                     "outcome": "Send proposal", "metadata": {"duration_seconds": 300}, "provider": "manual"},
                    {"occurred_at_local": "2026-11-12 09:00:00", "channel": "Email", "direction": "Inbound",
                     "event_type": "Completed", "subject": "Re: proposition", "content": None,
                     "outcome": None, "metadata": {}, "provider": "gmail"}]
    tasks = [{"created_at_local": "2026-11-10 10:05:00", "title": "Send proposal", "description": "",
              "due_at": "2026-11-13", "status": "A faire"}]
    objections = [{"occurred_at_local": "2026-11-10 10:01:00", "category": "No budget", "verbatim": "Pas avant mars",
                   "status": "Open", "stage": "In contact", "source": "manual"}]
    scores = [{"calculated_at_local": "2026-11-01 09:00:00", "global_score": 0, "fit_score": None,
               "engagement_score": 0, "intent_score": 0},
              {"calculated_at_local": "2026-11-02 09:00:00", "global_score": 0, "fit_score": None,
               "engagement_score": 0, "intent_score": 0},                       # pas de variation : ignoré
              {"calculated_at_local": "2026-11-12 09:05:00", "global_score": 34, "fit_score": None,
               "engagement_score": 40, "intent_score": 25}]
    stages = [{"changed_at_local": "2026-11-11 08:00:00", "from_stage": "To prospect",
               "to_stage": "In contact", "source": "pipeline"}]

    events = build_timeline(prospect, interactions, tasks, objections, scores, stages,
                            format_duration=lambda m: "5 min" if m.get("duration_seconds") else "")

    assert [e["title"] for e in events] == [
        "Score 0 → 34",
        "Email in · Completed",
        "Stage · To prospect → In contact",
        "Follow-up scheduled · Send proposal",
        "Objection · No budget",
        "Call out · Completed",
        "Prospect created",
    ]

    call = events[-2]
    assert call["detail"] == "Discovery — Budget en mars"
    assert call["meta"] == "5 min · Next step: Send proposal"
    assert call["source"] == "Manual"
    assert events[1]["source"] == "Gmail"
    assert events[-1]["meta"] == "Source: Import CSV"
    assert events[3]["meta"] == "Due 2026-11-13 · open"


def test_filter_timeline():
    events = [{"kind": "Interaction"}, {"kind": "Score"}, {"kind": "Stage"}]

    assert filter_timeline(events, ["Score", "Stage"]) == [{"kind": "Score"}, {"kind": "Stage"}]
    assert filter_timeline(events, []) == events


def test_timeline_from_real_records(thomas):
    database.add_interaction(thomas, "Note", "Internal", "Other", "Note", "Contexte", "",
                             occurred_at="2026-11-10 10:00:00")
    database.create_task(thomas, "Rappeler", "", "2026-11-20")
    objection_service.record_objection(thomas, "Bad timing")
    database.set_prospect_stage(thomas, "In contact")

    events = build_timeline(
        database.get_prospect_by_id(thomas), database.get_interactions(thomas), database.get_tasks(thomas),
        database.get_objections(thomas), database.get_score_history(thomas), database.get_stage_changes(thomas),
    )

    assert {e["kind"] for e in events} == {"Interaction", "Follow-up", "Objection", "Stage", "Prospect"}
