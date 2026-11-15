"""Tests de l'AI Copilot (phase 10.1).

Aucun test n'appelle l'API réelle : un FAUX client imite la réponse de
Claude. Les tests ne coûtent donc rien et ne sortent pas de l'ordinateur.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import database
import screens.prospect_details
from ai import claude_client
from ai.claude_client import CopilotError, generate
from core import copilot_service as copilot
from core import objection_service

MAIN = str(Path(__file__).resolve().parent.parent / "main.py")


# ---------- Faux client Claude ----------

class FakeClient:
    """Imite client.beta.messages.create et garde la dernière demande reçue."""

    def __init__(self, payload=None, stop_reason="end_turn", text=None):
        self.payload, self.stop_reason, self.text = payload, stop_reason, text
        self.request = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.request = kwargs
        body = self.text if self.text is not None else json.dumps(self.payload)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
            usage=SimpleNamespace(input_tokens=2500, output_tokens=800),
            model="claude-opus-5-5",
        )


@pytest.fixture
def record(thomas):
    """Thomas : un appel, une objection reliée, une réponse de playbook."""

    database.update_prospect(thomas, "Thomas", "Martins", "AlphaEngine", "SaaS", "thomas.martin@example.com",
                             "0612345678", "Head of Sales", "To prospect",
                             linkedin_url="https://www.linkedin.com/in/thomas-martins")
    call = database.add_interaction(thomas, "Call", "Outbound", "Completed", "Discovery",
                                    "Budget validé en mars", "Envoyer la proposition",
                                    occurred_at="2026-11-10 14:05:00")
    objection_service.record_objection(thomas, "Bad timing", "Pas avant mars", interaction_id=call)
    database.set_objection_response("Bad timing", "Proposer un rappel daté.")
    database.set_objection_response("No budget", "Réponse non utilisée.")

    prospect = database.get_prospect_by_id(thomas)
    context = copilot.build_context(prospect, database.get_interactions(thomas),
                                    database.get_objections(thomas), database.get_objection_responses())
    return thomas, call, context


# ---------- Contexte envoyé ----------

def test_context_never_contains_contact_details(record):
    _, call, context = record
    prompt = copilot.build_prompt("call_brief", context)

    for secret in ("thomas.martin@example.com", "0612345678", "linkedin.com/in/thomas-martins"):
        assert secret not in prompt
    assert "Budget validé en mars" in prompt and f'"I{call}"' in prompt


def test_context_ids_labels_and_playbook(record):
    _, call, context = record

    assert context["labels"][f"I{call}"] == "Call · 10/11 · Discovery"
    assert context["labels"]["P"] == "Prospect profile"
    assert context["playbook"] == {"Bad timing": "Proposer un rappel daté."}   # seulement les objections du prospect


def test_context_keeps_only_the_latest_interactions(record):
    thomas, _, _ = record
    for day in range(1, 13):
        database.add_interaction(thomas, "Note", "Internal", "Other", f"Note {day}", "", "",
                                 occurred_at=f"2026-11-{day:02d} 09:00:00")

    context = copilot.build_context(database.get_prospect_by_id(thomas), database.get_interactions(thomas), [], {})

    assert len(context["interactions"]) == copilot.MAX_INTERACTIONS


# ---------- Vérification de la réponse ----------

def test_facts_without_real_sources_are_removed(record):
    _, call, context = record
    data = {
        "facts": [{"text": "Budget validated for March.", "sources": [f"I{call}"]},
                  {"text": "Uses a competitor.", "sources": ["I999"]},          # source inventée
                  {"text": "Head of Sales.", "sources": []}],                     # aucune source
        "hypotheses": [{"text": "Might need approval.", "sources": []}],
        "questions": ["Who signs?", " "],
        "next_step": "Book a demo",
    }

    result = copilot.validate_output("call_brief", data, context)

    assert [f["text"] for f in result["facts"]] == ["Budget validated for March."]
    assert result["hypotheses"] == [{"text": "Might need approval.", "sources": []}]
    assert result["questions"] == ["Who signs?"]
    assert result["dropped"] == 2


def test_email_validation(record):
    _, call, context = record
    data = {"subject": " Next steps ", "body": "Hi Thomas,", "facts_used": [
        {"text": "Call on 10/11.", "sources": [f"I{call}", "O999"]}]}

    result = copilot.validate_output("email_draft", data, context)

    assert result["subject"] == "Next steps"
    assert result["facts_used"] == [{"text": "Call on 10/11.", "sources": [f"I{call}"]}]
    assert result["dropped"] == 0


def test_estimate_cost():
    assert copilot.estimate_cost({"input_tokens": 1_000_000, "output_tokens": 100_000}) == 6.0
    assert copilot.estimate_cost(None) is None


# ---------- Appel à Claude (faux client) ----------

def test_generate_sends_schema_effort_and_fallbacks():
    client = FakeClient(payload={"facts": [], "hypotheses": [], "questions": [], "next_step": ""})

    data, usage = generate("system", "prompt", copilot.CALL_BRIEF_SCHEMA, client=client)

    assert data["next_step"] == ""
    assert usage == {"input_tokens": 2500, "output_tokens": 800, "model": "claude-opus-5-5"}
    assert client.request["model"] == "claude-opus-5-5"
    assert client.request["fallbacks"] == "default"
    assert client.request["output_config"]["effort"] == "low"
    assert client.request["output_config"]["format"]["schema"] is copilot.CALL_BRIEF_SCHEMA


@pytest.mark.parametrize("client, message", [
    (FakeClient(payload={}, stop_reason="refusal"), "declined"),
    (FakeClient(payload={}, stop_reason="max_tokens"), "cut off"),
    (FakeClient(text="not json"), "could not be read"),
])
def test_generate_errors_are_readable(client, message):
    with pytest.raises(CopilotError, match=message):
        generate("system", "prompt", copilot.EMAIL_SCHEMA, client=client)


def test_generate_without_key(monkeypatch):
    monkeypatch.setattr(claude_client, "get_secret", lambda name: None)

    with pytest.raises(CopilotError, match="No API key"):
        generate("system", "prompt", copilot.EMAIL_SCHEMA)


# ---------- Interface : la fiche prospect ----------

def open_file(contact_id):
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.session_state["prospect_open"] = True
    at.session_state["details_prospect"] = contact_id
    return at.run()


def test_panel_is_off_by_default(record, monkeypatch):
    thomas, _, _ = record
    monkeypatch.setattr(screens.prospect_details, "ai_is_configured", lambda: True)

    at = open_file(thomas)

    assert not at.exception
    assert any("Enable AI features" in c.value for c in at.caption)
    assert f"ai_call_brief_btn_{thomas}" not in {b.key for b in at.button}


def test_call_brief_shows_sourced_facts(record, monkeypatch):
    thomas, call, _ = record
    database.set_setting(copilot.SETTING_ENABLED, True)
    monkeypatch.setattr(screens.prospect_details, "ai_is_configured", lambda: True)
    sent = {}

    def fake_generate(system, prompt, schema):
        sent["prompt"] = prompt
        return {"facts": [{"text": "Budget validated for March.", "sources": [f"I{call}"]},
                          {"text": "Invented fact.", "sources": ["I999"]}],
                "hypotheses": [], "questions": ["Who signs?"], "next_step": "Send the proposal"}, \
            {"input_tokens": 2500, "output_tokens": 800, "model": "claude-opus-5-5"}

    monkeypatch.setattr(screens.prospect_details, "ai_generate", fake_generate)

    at = open_file(thomas)
    at.button(key=f"ai_call_brief_btn_{thomas}").click().run()

    content = " | ".join(m.value for m in at.markdown) + " | " + " | ".join(c.value for c in at.caption)
    assert not at.exception
    assert "Budget validated for March." in content
    assert "Source: Call · 10/11 · Discovery" in content
    assert "Invented fact." not in content and "1 item(s) removed" in content
    assert "thomas.martin@example.com" not in sent["prompt"]


def test_ai_error_is_shown_not_raised(record, monkeypatch):
    thomas, _, _ = record
    database.set_setting(copilot.SETTING_ENABLED, True)
    monkeypatch.setattr(screens.prospect_details, "ai_is_configured", lambda: True)

    def failing(system, prompt, schema):
        raise CopilotError("The API key was rejected.")

    monkeypatch.setattr(screens.prospect_details, "ai_generate", failing)

    at = open_file(thomas)
    at.button(key=f"ai_email_draft_btn_{thomas}").click().run()

    assert not at.exception
    assert any("API key was rejected" in e.value for e in at.error)
    assert database.get_interactions(thomas)[0]["channel"] == "Call"          # rien n'a été enregistré


# ---------- Fournisseur alternatif : Google Gemini (faux client) ----------

from ai import gemini_client, providers


class FakeGemini:
    """Imite client.models.generate_content du kit google-genai."""

    def __init__(self, text='{"subject": "Hi", "body": "Hello", "facts_used": []}', finish="STOP", blocked=None):
        self.call = None
        response = SimpleNamespace(
            text=text,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
            prompt_feedback=SimpleNamespace(block_reason=blocked) if blocked else None,
            usage_metadata=SimpleNamespace(prompt_token_count=1200, candidates_token_count=300),
            model_version="gemini-3.5-flash-lite",
        )
        self.models = SimpleNamespace(generate_content=lambda **kw: self._record(kw, response))

    def _record(self, kwargs, response):
        self.call = kwargs
        return response


def test_gemini_sends_system_and_json_schema():
    client = FakeGemini()

    data, usage = gemini_client.generate("system rules", "prompt", copilot.EMAIL_SCHEMA, client=client)

    assert data["subject"] == "Hi"
    assert usage == {"input_tokens": 1200, "output_tokens": 300, "model": "gemini-3.5-flash-lite"}
    assert client.call["model"] == gemini_client.MODEL and client.call["contents"] == "prompt"
    config = client.call["config"]
    assert config.system_instruction == "system rules"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == copilot.EMAIL_SCHEMA


@pytest.mark.parametrize("client, message", [
    (FakeGemini(finish="SAFETY"), "declined"),
    (FakeGemini(blocked="PROHIBITED_CONTENT"), "declined"),
    (FakeGemini(finish="MAX_TOKENS"), "cut off"),
    (FakeGemini(text="oops"), "could not be read"),
    (FakeGemini(text=None), "no answer"),
])
def test_gemini_errors_are_readable(client, message):
    with pytest.raises(CopilotError, match=message):
        gemini_client.generate("s", "p", copilot.EMAIL_SCHEMA, client=client)


def test_provider_choice_is_stored(temp_db):
    assert providers.active_name() == "claude"

    database.set_setting(providers.SETTING_PROVIDER, "gemini")
    assert providers.active() is gemini_client

    database.set_setting(providers.SETTING_PROVIDER, "unknown")
    assert providers.active_name() == "claude"          # valeur inconnue : retour au défaut


def test_gemini_panel_shows_free_tier_warning(record, monkeypatch):
    thomas, _, _ = record
    database.set_setting(copilot.SETTING_ENABLED, True)
    database.set_setting(providers.SETTING_PROVIDER, "gemini")
    monkeypatch.setattr(gemini_client, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_client, "generate", lambda s, p, schema: (
        {"subject": "Next steps", "body": "Hello Thomas", "facts_used": []},
        {"input_tokens": 1200, "output_tokens": 300, "model": "gemini-3.8-flash"}))

    at = open_file(thomas)
    at.button(key=f"ai_email_draft_btn_{thomas}").click().run()

    captions = " | ".join(c.value for c in at.caption)
    assert not at.exception
    assert "Google may use the content" in captions
    assert "free tier" in captions and "$" not in captions.split("Generated by")[-1]
    assert "Hello Thomas" in at.code[0].value


def _server_error(code):
    from google.genai import errors
    return errors.ServerError(code, {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}})


def test_gemini_falls_back_to_the_light_model_when_overloaded():
    client = FakeGemini()
    calls = []
    answer = client.models.generate_content

    def flaky(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == gemini_client.MODEL:
            raise _server_error(504)
        return answer(**kwargs)

    client.models.generate_content = flaky
    data, _ = gemini_client.generate("s", "p", copilot.EMAIL_SCHEMA, client=client)

    assert calls == [gemini_client.MODEL, gemini_client.FALLBACK_MODEL]
    assert data["subject"] == "Hi"


def test_gemini_overloaded_everywhere_gives_a_clear_message():
    client = FakeGemini()

    def always_busy(**kwargs):
        raise _server_error(503)

    client.models.generate_content = always_busy

    with pytest.raises(CopilotError, match="overloaded"):
        gemini_client.generate("s", "p", copilot.EMAIL_SCHEMA, client=client)


def test_gemini_timeout_is_readable():
    client = FakeGemini()

    def hang(**kwargs):
        raise TimeoutError("read timed out")

    client.models.generate_content = hang

    with pytest.raises(CopilotError, match="did not answer"):
        gemini_client.generate("s", "p", copilot.EMAIL_SCHEMA, client=client)


# ---------- Phase 10.2 : chat sur toute la base ----------

from datetime import date as _date

import screens.copilot


def _global(today=_date(2026, 11, 15), **kw):
    prospects = database.get_all_prospects()
    return copilot.build_global_context(
        prospects, {p["id"]: {"global": 42, "temperature": "Warm"} for p in prospects},
        database.get_all_interactions(), database.get_objections(), database.get_all_tasks(),
        database.get_stages(), today=today, **kw)


def test_global_context_has_no_contact_details_and_sources(record):
    thomas, call, _ = record
    database.create_task(thomas, "Envoyer la proposition", "", "2026-11-12")
    context = _global()
    text = json.dumps(context["snapshot"], ensure_ascii=False)

    for secret in ("thomas.martin@example.com", "0612345678", "linkedin.com/in/thomas-martins"):
        assert secret not in text
    row = context["snapshot"]["prospects"][0]
    assert row["id"] == f"P{thomas}" and row["score"] == 42
    assert row["last_touch"]["id"] == f"I{call}" and row["last_touch"]["notes_excerpt"] == "Budget validé en mars"
    assert row["next_follow_up"] == {"due": "2026-11-12", "title": "Envoyer la proposition", "overdue": True}
    assert [o["category"] for o in row["open_objections"]] == ["Bad timing"]
    assert context["labels"][f"I{call}"] == "Call · 10/11 · Thomas Martins"
    assert context["contacts"][f"I{call}"] == thomas
    assert context["snapshot"]["totals"]["overdue_follow_ups"] == 1


def test_global_context_limit_keeps_priorities_first(temp_db):
    for i in range(5):
        database.create_prospect(f"P{i}", "Test", f"Co{i}", "SaaS", None, None, None)
    ids = [p["id"] for p in database.get_all_prospects()]

    context = _global(limit=2, priority_ids=[ids[3]])

    assert [r["id"] for r in context["snapshot"]["prospects"]][0] == f"P{ids[3]}"
    assert len(context["snapshot"]["prospects"]) == 2 and context["truncated"]
    assert context["snapshot"]["totals"]["prospects"] == 5


def test_notes_are_cut_to_an_excerpt(thomas):
    database.add_interaction(thomas, "Note", "Internal", "Other", "Long", "x" * 500, "")

    excerpt = _global()["snapshot"]["prospects"][0]["last_touch"]["notes_excerpt"]

    assert len(excerpt) == copilot.NOTES_EXCERPT + 1 and excerpt.endswith("…")


def test_chat_prompt_contains_history_and_question(record):
    context = _global()
    history = [{"role": "user", "content": f"q{i}"} for i in range(10)]

    prompt = copilot.build_chat_prompt("Who is hot?", history, context)

    assert prompt.endswith("Question: Who is hot?")
    assert "USER: q9" in prompt and "USER: q3" not in prompt          # seulement les 6 derniers


def test_validate_chat_drops_unsourced_and_lists_cited_prospects(record):
    thomas, call, _ = record
    context = _global()
    data = {"answer": "Follow up with Thomas.",
            "facts": [{"text": "Thomas has an overdue follow-up.", "sources": [f"I{call}", f"P{thomas}"]},
                      {"text": "Invented.", "sources": ["P999"]}],
            "hypotheses": [], "out_of_scope": False}

    result = copilot.validate_chat(data, context)

    assert [f["text"] for f in result["facts"]] == ["Thomas has an overdue follow-up."]
    assert result["dropped"] == 1 and result["prospects"] == [thomas]


# ---------- Interface du chat ----------

def open_copilot():
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    at.sidebar.radio[0].set_value(next(o for o in at.sidebar.radio[0].options if o.endswith("AI Copilot"))).run()
    return at


def test_chat_is_off_until_enabled(record, monkeypatch):
    monkeypatch.setattr(screens.copilot, "ai_is_configured", lambda: True)
    at = open_copilot()

    assert not at.exception
    assert "The AI Copilot is off" in " ".join(m.value for m in at.markdown)
    assert len(at.chat_input) == 0


def test_chat_answers_with_sources_and_open_button(record, monkeypatch):
    thomas, call, _ = record
    database.set_setting(copilot.SETTING_ENABLED, True)
    monkeypatch.setattr(screens.copilot, "ai_is_configured", lambda: True)
    sent = {}

    def fake(system, prompt, schema):
        sent["prompt"], sent["schema"] = prompt, schema
        return {"answer": "- Thomas Martins: follow up on the proposal.",
                "facts": [{"text": "Call on 10/11 about the budget.", "sources": [f"I{call}"]}],
                "hypotheses": [], "out_of_scope": False}, \
            {"input_tokens": 900, "output_tokens": 120, "model": "gemini-3.5-flash-lite"}

    monkeypatch.setattr(screens.copilot, "ai_generate", fake)

    at = open_copilot()
    at.chat_input(key="copilot_input").set_value("Who should I follow up with?").run()

    assert not at.exception
    assert sent["schema"] is copilot.CHAT_SCHEMA
    assert "Question: Who should I follow up with?" in sent["prompt"]
    assert "thomas.martin@example.com" not in sent["prompt"]
    assert "Thomas Martins: follow up on the proposal." in " ".join(m.value for m in at.markdown)
    open_button = at.button(key=f"copilot_open_1_{thomas}")
    assert open_button.label == "Open Thomas Martins"

    open_button.click().run()
    assert at.session_state["prospect_open"]
    assert any("Thomas Martins" in t.value for t in at.title)          # la fiche de Thomas est ouverte


def test_chat_error_is_shown(record, monkeypatch):
    database.set_setting(copilot.SETTING_ENABLED, True)
    monkeypatch.setattr(screens.copilot, "ai_is_configured", lambda: True)

    def failing(system, prompt, schema):
        raise CopilotError("Gemini is overloaded or unavailable (503).")

    monkeypatch.setattr(screens.copilot, "ai_generate", failing)

    at = open_copilot()
    at.chat_input(key="copilot_input").set_value("Hello").run()

    assert not at.exception
    assert any("overloaded" in e.value for e in at.error)
