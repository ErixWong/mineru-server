import sqlite3
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import mineru_mcp.admin_auth as admin_auth
from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase


def _setup_admin_database(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    admin_auth.init_default_admin()
    return TaskDatabase(db_path=str(tmp_path / "tasks.db"))


def _login():
    return admin_auth.admin_login("admin", admin_auth.get_default_admin_password())


def test_admin_session_login_verification_and_logout(tmp_path, monkeypatch):
    db = _setup_admin_database(tmp_path, monkeypatch)
    result = _login()

    session = admin_auth.verify_session(result["session_token"])
    assert session is not None
    assert session["username"] == "admin"
    assert session["csrf_token"] == result["csrf_token"]

    assert admin_auth.admin_logout(result["session_token"]) is True
    assert admin_auth.verify_session(result["session_token"]) is None
    assert db.get_admin_session(admin_auth._hash_token(result["session_token"])) is None


def test_expired_admin_session_is_rejected_and_deleted(tmp_path, monkeypatch):
    db = _setup_admin_database(tmp_path, monkeypatch)
    result = _login()
    token_hash = admin_auth._hash_token(result["session_token"])
    expired_at = (datetime.now() - timedelta(seconds=1)).isoformat()

    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE admin_sessions SET expires_at = ? WHERE token_hash = ?",
            (expired_at, token_hash),
        )

    assert admin_auth.verify_session(result["session_token"]) is None
    assert db.get_admin_session(token_hash) is None


def test_admin_session_survives_recreated_database_store(tmp_path, monkeypatch):
    _setup_admin_database(tmp_path, monkeypatch)
    result = _login()

    restarted_store = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    monkeypatch.setattr(admin_auth, "_get_db", lambda: restarted_store)

    persisted_session = restarted_store.get_admin_session(
        admin_auth._hash_token(result["session_token"])
    )
    assert persisted_session is not None
    assert admin_auth.verify_session(result["session_token"])["username"] == "admin"


def test_password_change_invalidation_removes_persisted_sessions(tmp_path, monkeypatch):
    _setup_admin_database(tmp_path, monkeypatch)
    result = _login()

    assert admin_auth.invalidate_all_sessions("admin") == 1
    assert admin_auth.verify_session(result["session_token"]) is None


def test_admin_auth_endpoints_keep_401_error_semantics(tmp_path, monkeypatch):
    _setup_admin_database(tmp_path, monkeypatch)
    client = TestClient(create_api_app())

    missing_session = client.get("/admin/me")
    assert missing_session.status_code == 401
    assert missing_session.json()["detail"]["error"] == "UNAUTHORIZED"

    invalid_login = client.post(
        "/admin/login",
        json={"username": "invalid-session-semantics", "password": "incorrect"},
        headers={"Origin": "http://testserver"},
    )
    assert invalid_login.status_code == 401
    assert invalid_login.json()["detail"]["error"] == "AUTH_FAILED"
