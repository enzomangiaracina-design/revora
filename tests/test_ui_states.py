"""Tests d'interface (P0.4) : états vides et gestion des erreurs.

Concept : AppTest exécute main.py comme un vrai utilisateur, sans navigateur.
La fixture temp_db redirige la base vers un fichier temporaire vide :
revora.db n'est jamais touchée.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import screens.copilot

MAIN = str(Path(__file__).resolve().parent.parent / "main.py")

PAGES = ["Overview", "Prospects", "Prospecting Pipeline", "Activity", "Objections",
         "AI Copilot", "Performance", "Settings"]


def open_page(page):
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    labels = at.sidebar.radio[0].options
    at.sidebar.radio[0].set_value(next(label for label in labels if label.endswith(
        "Pipeline" if page == "Prospecting Pipeline" else page))).run()
    return at


def texts(at):
    return " | ".join(m.value for m in at.markdown) + " | " + " | ".join(c.value for c in at.caption)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_on_an_empty_database(temp_db, page):
    at = open_page(page)

    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page, expected_title, expected_button", [
    ("Overview", "Your prospect database is empty", "Add a prospect"),
    ("Prospects", "No prospect registered yet", "Import a CSV file"),
    ("Prospecting Pipeline", "Your pipeline is empty", "Add a prospect"),
    ("Activity", "No activity recorded yet", "Log a call or email"),
    ("Objections", "No objection recorded for this period", "Log a call or email"),
    ("AI Copilot", "The AI Copilot is not available yet", None),
    ("Performance", "No interaction recorded in this period", "Log a call or email"),
])
def test_empty_states_explain_what_to_do_next(temp_db, page, expected_title, expected_button):
    at = open_page(page)

    assert expected_title in texts(at)
    if expected_button:
        assert expected_button in [b.label for b in at.button]


def test_empty_state_action_navigates(temp_db):
    at = open_page("Overview")
    [b for b in at.button if b.label == "Import a CSV file"][0].click().run()

    assert at.session_state["nav_page"] == "Prospects"
    assert at.session_state["prospects_tabs"] == "Import CSV"
    assert not at.exception


def test_unexpected_error_is_shown_cleanly(temp_db, monkeypatch):
    def broken(ctx):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(screens.copilot, "render", broken)

    at = open_page("AI Copilot")

    assert not at.exception                                   # pas de trace brute
    assert "This page hit an unexpected error" in texts(at)
    assert "simulated failure" in " ".join(c.value for c in at.code)
    assert {"Try again", "Back to Overview"} <= {b.label for b in at.button}

    [b for b in at.button if b.label == "Back to Overview"][0].click().run()
    assert at.session_state["nav_page"] == "Overview"


def test_streamlit_reruns_are_not_caught_by_the_error_guard(thomas):
    """st.rerun() (après une création) doit continuer à fonctionner."""

    at = open_page("Prospects")
    form = next(w.form_id for w in at.text_input if (w.form_id or "").startswith("create_form_"))
    fields = {w.label: w for w in at.text_input if w.form_id == form}
    fields["First name *"].set_value("Ana"); fields["Last name *"].set_value("Lopez")
    fields["Company *"].set_value("Acme")
    [b for b in at.button if b.label == "Create prospect"][0].click().run()

    assert not at.exception
    assert "This page hit an unexpected error" not in texts(at)
    assert any("succes" in s.value for s in at.success)
