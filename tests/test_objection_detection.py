"""Tests de la détection des objections par IA (suggestions à confirmer)."""

import database
from core.copilot_service import (
    OBJECTION_SCHEMA,
    build_objection_context,
    build_objection_prompt,
    validate_objections,
)
from core.objection_service import DEFAULT_CATEGORIES, record_objection
from core.timeline_service import build_timeline


def interaction(id_, notes, subject="Appel", when="2026-11-10 14:00:00"):
    return {"id": id_, "occurred_at_local": when, "channel": "Call", "direction": "Outbound",
            "event_type": "Completed", "subject": subject, "content": notes, "outcome": ""}


NOTES = "Bon échange. Il m’a dit : « Pas avant mars, budget gelé jusque-là. » Rappel prévu."


def context(recorded=()):
    interactions = [interaction(12, NOTES), interaction(13, "", subject=""), interaction(14, "RAS")]
    objections = [{"interaction_id": i, "category": c} for i, c in recorded]
    return build_objection_context(interactions, objections, DEFAULT_CATEGORIES)


def test_context_sends_only_interactions_with_notes():
    ctx = context()

    assert [i["id"] for i in ctx["interactions"]] == ["I12", "I14"]       # I13 vide : non envoyée
    assert "email" not in build_objection_prompt(ctx)                     # aucune coordonnée
    assert "Pas avant mars" in build_objection_prompt(ctx)


def test_exact_quote_is_kept_and_category_normalized():
    data = {"objections": [{"interaction": "I12", "category": "bad timing",
                            "wording": "pas avant mars, budget gelé jusque-là.", "why": "Timing"}]}
    result = validate_objections(data, context())

    assert result["dropped"] == 0
    suggestion = result["suggestions"][0]
    assert suggestion["category"] == "Bad timing"                         # catégorie existante retrouvée
    assert suggestion["interaction_id"] == 12 and suggestion["label"].startswith("Call · 10/11")


def test_invented_or_unknown_suggestions_are_dropped():
    data = {"objections": [
        {"interaction": "I12", "category": "No budget", "wording": "We have no budget at all", "why": ""},  # traduit/inventé
        {"interaction": "I99", "category": "No budget", "wording": "budget gelé", "why": ""},               # échange inconnu
        {"interaction": "I12", "category": "", "wording": "budget gelé", "why": ""},                       # sans catégorie
        {"interaction": "I12", "category": "No budget", "wording": "", "why": ""},                         # sans citation
    ]}
    result = validate_objections(data, context())

    assert result["suggestions"] == [] and result["dropped"] == 4


def test_already_recorded_and_duplicates_are_dropped():
    item = {"interaction": "I12", "category": "Bad timing", "wording": "Pas avant mars", "why": ""}

    assert validate_objections({"objections": [item]}, context([(12, "Bad timing")]))["dropped"] == 1
    twice = validate_objections({"objections": [item, item]}, context())
    assert len(twice["suggestions"]) == 1 and twice["dropped"] == 1


def test_new_category_is_allowed_but_kept_as_suggested():
    data = {"objections": [{"interaction": "I12", "category": "Budget freeze",
                            "wording": "budget gelé", "why": ""}]}

    assert validate_objections(data, context())["suggestions"][0]["category"] == "Budget freeze"


def test_schema_requires_a_quote_and_an_interaction():
    item = OBJECTION_SCHEMA["properties"]["objections"]["items"]
    assert set(item["required"]) == {"interaction", "category", "wording", "why"}


def test_confirmed_suggestion_is_saved_with_ai_source(thomas):
    interaction_id = database.add_interaction(thomas, "Call", "Outbound", "Completed", "Appel", NOTES, "",
                                              occurred_at="2026-11-10 14:00:00")
    ok, _ = record_objection(thomas, "Bad timing", "Pas avant mars", interaction_id=interaction_id, source="ai")

    assert ok
    objection = database.get_objections(thomas)[0]
    assert objection["source"] == "ai" and objection["interaction_id"] == interaction_id
    assert objection["occurred_at_local"].startswith("2026-11-10")      # date de l'échange d'origine

    event = next(e for e in build_timeline(database.get_prospect_by_id(thomas), [], [], database.get_objections(thomas), [], [])
                 if e["kind"] == "Objection")
    assert event["source"] == "AI (confirmed)"


def test_manual_remains_the_default_source(thomas):
    record_objection(thomas, "No budget")
    assert database.get_objections(thomas)[0]["source"] == "manual"
