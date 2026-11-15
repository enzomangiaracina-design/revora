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
