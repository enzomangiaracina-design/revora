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
    assert any("successfully" in s.value for s in at.success)


# ---------- P1 : actions rapides du Today's Focus ----------

from datetime import date, timedelta

import database


@pytest.fixture
def focus_data(temp_db):
    """Deux prospects : Paul (relance en retard) et Lina (jamais contactée)."""

    database.create_prospect("Paul", "Roux", "Fintra", "Finance", "paul@x.example", "0611", None)
    database.create_prospect("Lina", "Faure", "Medivia", "Santé", "lina@x.example", None, None)
    ids = {p["first_name"]: p["id"] for p in database.get_all_prospects()}
    database.create_task(ids["Paul"], "Envoyer la proposition", "",
                         (date.today() - timedelta(days=2)).isoformat())
    return ids


def focus_names(at):
    return [m.value for m in at.markdown if "**" in m.value and ("Paul Roux" in m.value or "Lina Faure" in m.value)]


def test_focus_rows_show_type_due_and_reason(focus_data):
    at = open_page("Overview")
    content = texts(at)

    assert "Follow-up: Envoyer la proposition" in content
    assert "Overdue 2 d" in content
    assert "Why: Follow-up due" in content
    assert "First contact: email" in content          # Lina : pas de téléphone, un email
    assert "Why: Never contacted · added" in content


def test_done_completes_the_follow_up(focus_data):
    at = open_page("Overview")
    at.button(key=f"focus_done_{focus_data['Paul']}").click().run()

    assert [t["status"] for t in database.get_tasks(focus_data["Paul"])] == ["Terminee"]
    assert any("Follow-up completed" in s.value for s in at.success)


def test_postpone_moves_the_due_date(focus_data):
    at = open_page("Overview")
    at.button(key=f"focus_postpone_{focus_data['Paul']}_3").click().run()

    due = database.get_tasks(focus_data["Paul"])[0]["due_at"]
    assert due == (date.today() + timedelta(days=3)).isoformat()
    # Plus de relance en retard : Paul reste prioritaire uniquement parce qu'il n'a jamais été contacté
    content = texts(at)
    assert "Overdue" not in content
    assert "First contact: call" in content
    assert f"Due {(date.today() + timedelta(days=3)).strftime('%d/%m')}" in content


def test_not_now_sets_aside_then_restore(focus_data):
    at = open_page("Overview")
    at.text_input(key=f"focus_reason_{focus_data['Lina']}").set_value("En congés")
    at.button(key=f"focus_aside_{focus_data['Lina']}_7").click().run()

    snooze = database.get_active_snoozes(date.today().isoformat())[focus_data["Lina"]]
    assert snooze["reason"] == "En congés"
    assert snooze["until"] == (date.today() + timedelta(days=7)).isoformat()
    assert not any("Lina Faure" in name for name in focus_names(at))
    assert "1 prospect(s) set aside" in texts(at)

    at.button(key="focus_restore").click().run()
    assert database.get_active_snoozes(date.today().isoformat()) == {}
    assert any("Lina Faure" in name for name in focus_names(at))


def test_expired_snooze_is_ignored(focus_data):
    database.snooze_prospect(focus_data["Lina"], (date.today() - timedelta(days=1)).isoformat())

    assert database.get_active_snoozes(date.today().isoformat()) == {}


# ---------- P2 : objection reliée à son échange ----------
# (AppTest ne pilote pas les st.dialog : la fenêtre est vérifiée dans le navigateur)

def test_objections_log_shows_the_source_interaction(focus_data):
    from core import objection_service
    paul = focus_data["Paul"]
    call_id = database.add_interaction(paul, "Call", "Outbound", "Completed", "Discovery", "", "",
                                       occurred_at="2026-11-10 14:05:00")
    objection_service.record_objection(paul, "No budget", interaction_id=call_id)

    at = open_page("Objections")
    log = at.dataframe[-1].value

    assert not at.exception
    assert list(log["Raised during"]) == ["Call · 10/11 14:05 · Discovery"]


# ---------- P2.2 : Activity, filtre par source et état des synchronisations ----------

def test_activity_source_filter_and_sync_line(focus_data):
    from datetime import datetime as dt, timezone
    now = dt.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    database.add_interaction(focus_data["Paul"], "Call", "Outbound", "Completed", "Manual call", "", "")
    database.add_external_interaction(focus_data["Lina"], "gmail", "msg-1", "Email", "Inbound",
                                      "Completed", now, subject="Synced email")

    at = open_page("Activity")
    assert not at.exception
    assert "Sync:" in texts(at) and "not connected" in texts(at)
    assert sorted(at.dataframe[0].value["Source"]) == ["Gmail", "Manual"]

    at.multiselect(key="activity_sources").set_value(["Gmail"]).run()
    assert list(at.dataframe[0].value["Subject"]) == ["Synced email"]


# ---------- P2.3 : Performance, faible volume et filtre par commercial ----------

def test_performance_low_volume_and_owner_filter(temp_db):
    database.create_prospect("Paul", "Roux", "Fintra", "Finance", None, "0611", None)
    database.create_prospect("Lina", "Faure", "Medivia", "Santé", None, "0622", None)
    ids = {p["first_name"]: p["id"] for p in database.get_all_prospects()}
    p = database.get_prospect_by_id(ids["Paul"])
    database.update_prospect(ids["Paul"], "Paul", "Roux", "Fintra", "Finance", None, "0611", None,
                             p["status"], owner="Lea")
    for name in ("Paul", "Lina"):
        database.add_interaction(ids[name], "Call", "Outbound", "Completed", "", "", "")

    at = open_page("Performance")
    assert not at.exception
    assert ":orange[:material/warning:] Connection rate" in [m.label for m in at.metric]
    assert "connection rate: 2 calls" in texts(at)

    at.multiselect(key="performance_owners").set_value(["Lea"]).run()
    assert "connection rate: 1 call" in texts(at)


# ---------- P2.4 : confirmation avant une étape fermée ----------

def open_file(contact_id):
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.session_state["prospect_open"] = True
    at.session_state["details_prospect"] = contact_id
    return at.run()


def test_open_stage_moves_immediately(focus_data):
    paul = focus_data["Paul"]
    at = open_file(paul)
    at.selectbox(key=f"stage_select_{paul}").set_value("In contact").run()

    assert database.get_prospect_by_id(paul)["status"] == "In contact"
    assert not at.exception


def test_closed_stage_asks_for_confirmation(focus_data):
    paul = focus_data["Paul"]
    at = open_file(paul)
    at.selectbox(key=f"stage_select_{paul}").set_value("Disqualified").run()

    # Rien n'est appliqué tant que ce n'est pas confirmé ; le sélecteur reste sur l'étape actuelle
    assert database.get_prospect_by_id(paul)["status"] == "To prospect"
    assert at.selectbox(key=f"stage_select_{paul}").value == "To prospect"
    assert "to the closed stage" in texts(at)

    at.button(key="stage_change_cancel").click().run()
    assert database.get_prospect_by_id(paul)["status"] == "To prospect"
    assert "to the closed stage" not in texts(at)

    at.selectbox(key=f"stage_select_{paul}").set_value("Disqualified").run()
    at.button(key="stage_change_confirm").click().run()
    assert database.get_prospect_by_id(paul)["status"] == "Disqualified"
    assert [c["to_stage"] for c in database.get_stage_changes(paul)] == ["Disqualified"]
    assert not at.exception


def test_stage_definition_edited_in_stages_view(temp_db):
    at = open_page("Prospecting Pipeline")
    at.segmented_control(key="pipeline_view").set_value("Stages").run()
    first = database.get_stages()[0]
    at.text_input(key=f"stage_definition_{first['id']}").set_value("Jamais contacté").run()
    at.button(key=f"stage_definition_save_{first['id']}").click().run()

    assert database.get_stages()[0]["definition"] == "Jamais contacté"
    assert not at.exception


# ---------- Formulaire d'interaction : la saisie reste en cas d'erreur ----------

def _log_form(at):
    form = next(w.form_id for w in at.text_input if (w.form_id or "").startswith("log_activity_form_"))
    return form, {w.label: w for w in at.text_input if w.form_id == form}


def test_interaction_form_keeps_input_on_error_and_clears_on_success(focus_data):
    at = open_page("Activity")
    at.tabs  # onglets rendus
    form, fields = _log_form(at)
    fields["Next step"].set_value("Rappeler mardi")
    [b for b in at.button if b.label == "Save interaction"][0].click().run()

    # Erreur (ni objet ni note) : le champ saisi est toujours là
    assert any("subject or a note" in e.value for e in at.error)
    assert _log_form(at)[1]["Next step"].value == "Rappeler mardi"

    _log_form(at)[1]["Subject"].set_value("Premier appel")
    [b for b in at.button if b.label == "Save interaction"][0].click().run()

    assert not at.exception
    new_form, fields = _log_form(at)
    assert new_form != form and fields["Subject"].value == ""          # formulaire neuf après succès
    assert len(database.get_all_interactions()) == 1


def test_timeline_shows_edit_only_for_manual_interactions(focus_data):
    paul = focus_data["Paul"]
    manual = database.add_interaction(paul, "Call", "Outbound", "Completed", "Appel", "", "")
    database.add_external_interaction(paul, "gmail", "m-9", "Email", "Inbound", "Completed",
                                      "2026-11-14 09:00:00", subject="Synced")
    synced = next(i["id"] for i in database.get_interactions(paul) if i["provider"] == "gmail")

    at = open_file(paul)
    keys = {b.key for b in at.button}

    assert f"edit_interaction_{manual}" in keys
    assert f"edit_interaction_{synced}" not in keys
