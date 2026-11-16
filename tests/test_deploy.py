"""Tests du déploiement Render (phase 12.2). Rien n'est mis en ligne."""

import importlib.util
import tomllib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import database
from core.auth_service import sign_in_required
from core.user_service import create_user, ensure_admin

ROOT = Path(__file__).resolve().parent.parent
MAIN = str(ROOT / "main.py")


def load_start_script():
    spec = importlib.util.spec_from_file_location("render_start", ROOT / "deploy" / "render_start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sign_in_required_flag():
    assert sign_in_required({"REVORA_REQUIRE_SIGN_IN": "1"})
    assert sign_in_required({"REVORA_REQUIRE_SIGN_IN": "true"})
    assert not sign_in_required({})
    assert not sign_in_required({"REVORA_REQUIRE_SIGN_IN": "0"})


def test_online_version_never_opens_without_sign_in(temp_db, monkeypatch):
    monkeypatch.setenv("REVORA_REQUIRE_SIGN_IN", "1")
    create_user("Léa Martin", "SDR")                      # même avec une équipe : rien ne s'ouvre

    at = AppTest.from_file(MAIN, default_timeout=60).run()

    assert not at.exception
    assert [t.value for t in at.title] == ["Sign-in is not configured"]
    assert not at.sidebar.radio and not at.sidebar.selectbox     # ni navigation ni « Signed in as »


def test_ensure_admin(temp_db):
    assert ensure_admin("Boss@Corp.example", "Boss")[0]
    admin = database.get_users()[0]
    assert (admin["email"], admin["role"], admin["active"]) == ("boss@corp.example", "Manager", 1)

    database.update_user(admin["id"], role="SDR", active=False)
    assert ensure_admin("boss@corp.example")[0]                    # rétabli, pas dupliqué
    assert len(database.get_users()) == 1
    assert database.get_users()[0]["role"] == "Manager" and database.get_users()[0]["active"] == 1

    assert not ensure_admin("not-an-email")[0]
    assert not ensure_admin("")[0]


def test_start_script_prepares_demo_once_and_admin(tmp_path, monkeypatch):
    start = load_start_script()
    target = tmp_path / "storage" / "demo.db"
    target.parent.mkdir()
    env = {"REVORA_DATABASE": str(target), "REVORA_ADMIN_EMAIL": "admin@corp.example"}
    monkeypatch.setattr(database, "DATABASE_PATH", database.DATABASE_PATH)   # restauré après le test

    start.prepare(env)
    assert target.exists() and len(database.get_all_prospects()) == 20
    database.create_prospect("Anna", "Petit", "Beta", "SaaS", "anna@example.com", "", "CFO")

    start.prepare(env)                                              # redémarrage : rien n'est écrasé
    assert len(database.get_all_prospects()) == 21
    assert [u["email"] for u in database.get_users()] == ["admin@corp.example"]


def test_start_script_refuses_a_relative_database(monkeypatch):
    start = load_start_script()
    with pytest.raises(SystemExit):
        start.prepare({"REVORA_DATABASE": "demo.db"})
    with pytest.raises(SystemExit):
        start.prepare({})


def test_streamlit_command_matches_render():
    command = load_start_script().streamlit_command({"PORT": "10000"})
    assert command[:3] == ["streamlit", "run", str(ROOT / "main.py")]
    assert command[command.index("--server.port") + 1] == "10000"
    assert command[command.index("--server.address") + 1] == "0.0.0.0"
    assert command[command.index("--secrets.files") + 1] == "/etc/secrets/secrets.toml"


def test_render_blueprint_has_no_secret_values():
    text = (ROOT / "render.yaml").read_text()
    for name in ("GEMINI_API_KEY", "REVORA_ADMIN_EMAIL", "client_secret", "cookie_secret"):
        if name in text:
            line = next(l for l in text.splitlines() if name in l)
            following = text.splitlines()[text.splitlines().index(line) + 1]
            assert "sync: false" in following, name                     # valeur demandée par Render
    assert "region: frankfurt" in text and "mountPath: /opt/render/project/src/storage" in text
    assert "REVORA_REQUIRE_SIGN_IN" in text
