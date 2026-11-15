"""Tests de la vraie connexion (phase 12.1). Aucun vrai fournisseur n'est contacté."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import database
import screens.shared as shared
from core.auth_service import can_manage_team, is_configured, missing_settings, resolve_user
from core.user_service import create_user, set_email

MAIN = str(Path(__file__).resolve().parent.parent / "main.py")

AUTH = {
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "test-cookie-secret",
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


class BrokenSecrets:
    """Imite st.secrets quand secrets.toml est absent : la lecture lève une erreur."""

    def get(self, key, default=None):
        raise FileNotFoundError("no secrets.toml")


def test_configuration_detection():
    assert not is_configured({})
    assert not is_configured(BrokenSecrets())                     # fichier absent : pas de connexion
    assert missing_settings({"auth": {**AUTH, "client_secret": ""}}) == ["client_secret"]
    assert not is_configured({"auth": {**AUTH, "client_secret": ""}})
    assert is_configured({"auth": AUTH})


def test_resolve_user_by_email():
    users = [{"id": 1, "name": "Léa", "email": "lea@corp.example", "active": 1, "role": "SDR"},
             {"id": 2, "name": "Old", "email": "old@corp.example", "active": 0, "role": "SDR"}]

    assert resolve_user(users, {"email": " LEA@corp.example "})[0]["id"] == 1
    assert resolve_user(users, {"email": "lea@corp.example", "email_verified": False})[0] is None
    assert "deactivated" in resolve_user(users, {"email": "old@corp.example"})[1]
    assert "not in the REVORA team" in resolve_user(users, {"email": "x@corp.example"})[1]
    assert resolve_user(users, {"name": "No email"})[0] is None


def test_only_managers_manage_the_team_when_sign_in_is_on():
    assert can_manage_team(None, auth_enabled=False)              # prototype local : comme avant
    assert can_manage_team({"role": "Manager"}, auth_enabled=True)
    assert not can_manage_team({"role": "SDR"}, auth_enabled=True)


def test_team_emails_are_validated_and_unique(temp_db):
    assert create_user("Léa Martin", "SDR", " Lea@Corp.example ")[0]
    assert database.get_users()[0]["email"] == "lea@corp.example"
    assert not create_user("Hugo", "SDR", "not-an-email")[0]
    assert not create_user("Hugo", "SDR", "LEA@corp.example")[0]      # même email, autre casse

    create_user("Hugo", "SDR")
    hugo = next(u for u in database.get_users() if u["name"] == "Hugo")
    assert not set_email(hugo["id"], "lea@corp.example")[0]
    assert set_email(hugo["id"], "hugo@corp.example")[0]
    assert set_email(hugo["id"], "")[1] == "Email removed."


def test_without_configuration_nothing_changes(temp_db):
    create_user("Léa Martin", "SDR")
    at = AppTest.from_file(MAIN, default_timeout=60).run()

    assert not at.exception
    assert any(s.label == "Signed in as" for s in at.sidebar.selectbox)


def test_sign_in_screen_blocks_the_app(temp_db):
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.secrets["auth"] = AUTH
    at.run()

    assert not at.exception
    assert [t.value for t in at.title] == ["Sign in to REVORA"]
    assert not at.sidebar.radio                                         # pas de navigation avant connexion


def test_signed_in_member_and_stranger(temp_db, monkeypatch):
    create_user("Nina Roy", "Manager", "nina@corp.example")

    monkeypatch.setattr(shared, "_identity_claims", lambda: {"email": "stranger@corp.example"})
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.secrets["auth"] = AUTH
    at.run()
    assert [t.value for t in at.title] == ["Access not granted"]

    monkeypatch.setattr(shared, "_identity_claims", lambda: {"email": "nina@corp.example"})
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.secrets["auth"] = AUTH
    at.run()
    assert not at.exception
    assert any("Signed in as **Nina Roy**" in c.value for c in at.sidebar.caption)
    assert not any(s.label == "Signed in as" for s in at.sidebar.selectbox)  # plus de menu sans mot de passe

    at.sidebar.radio[0].set_value("Settings").run()
    assert not at.exception
    assert any("Sign-in is on" in c.value for c in at.caption)


def test_signed_in_manager_cannot_lock_herself_out(temp_db, monkeypatch):
    create_user("Nina Roy", "Manager", "nina@corp.example")
    create_user("Léa Martin", "SDR", "lea@corp.example")
    ids = {u["name"]: u["id"] for u in database.get_users()}

    monkeypatch.setattr(shared, "_identity_claims", lambda: {"email": "nina@corp.example"})
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.secrets["auth"] = AUTH
    at.run()
    at.sidebar.radio[0].set_value("Settings").run()

    at.selectbox(key=f"team_role_{ids['Nina Roy']}").select("SDR").run()
    assert not at.exception
    assert at.selectbox(key=f"team_role_{ids['Nina Roy']}").value == "Manager"     # rien n'a changé
    assert next(u for u in database.get_users() if u["name"] == "Nina Roy")["role"] == "Manager"

    at.selectbox(key=f"team_role_{ids['Léa Martin']}").select("Manager").run()     # un autre : autorisé
    assert next(u for u in database.get_users() if u["name"] == "Léa Martin")["role"] == "Manager"


def test_signed_in_sdr_cannot_edit_the_team(temp_db, monkeypatch):
    create_user("Léa Martin", "SDR", "lea@corp.example")

    monkeypatch.setattr(shared, "_identity_claims", lambda: {"email": "lea@corp.example"})
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.secrets["auth"] = AUTH
    at.run()
    at.sidebar.radio[0].set_value("Settings").run()

    assert not at.exception
    assert at.selectbox(key=f"team_role_{database.get_users()[0]['id']}").disabled
    assert any("Only managers can change the team" in c.value for c in at.caption)
