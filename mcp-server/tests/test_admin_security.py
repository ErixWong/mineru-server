import importlib
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import mineru_mcp.admin_auth as admin_auth_module
from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password, verify_password
from mineru_mcp.api import create_api_app
from mineru_mcp.app import create_unified_app
from mineru_mcp.auth import resolve_principal
from mineru_mcp.config import reset_config
from mineru_mcp.errors import MCPError
from mineru_mcp.task_queue import TaskDatabase


TEST_CALLER_KEY_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _set_common_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_CALLER_KEY_MASTER_KEY", TEST_CALLER_KEY_MASTER_KEY)
    reset_config()


def _create_test_caller(db: TaskDatabase, caller_id: str, api_key: str, **updates):
    db.create_caller(
        caller_id=caller_id,
        name=caller_id,
        api_key=api_key,
        api_key_prefix=api_key[:4],
        api_key_suffix=api_key[-4:],
    )
    if updates:
        db.update_caller(caller_id, **updates)


def _login_admin(client: TestClient):
    response = client.post(
        "/admin/login",
        json={"username": "admin", "password": get_default_admin_password()},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response


def test_fresh_database_user_version_matches_schema_version(tmp_path):
    db_path = tmp_path / "tasks.db"
    TaskDatabase(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == TaskDatabase.SCHEMA_VERSION


def test_admin_write_requires_csrf_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    _login_admin(client)

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "CSRF_REQUIRED"


def test_admin_write_accepts_valid_csrf_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"]
    assert response.headers["cache-control"] == "no-store"

    list_response = client.get("/admin/callers?include_disabled=true")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert "api_key" not in list_payload[0]
    assert "api_key_encrypted" not in list_payload[0]
    assert "api_key_hash" not in list_payload[0]
    assert "api_key_key_id" not in list_payload[0]


def test_admin_reveal_caller_key_requires_write_controls_and_does_not_auth_disabled_or_expired(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    create_response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert create_response.status_code == 200
    caller_id = create_response.json()["caller_id"]
    api_key = create_response.json()["api_key"]

    first_reveal = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )
    second_reveal = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert first_reveal.status_code == 200
    assert second_reveal.status_code == 200
    assert first_reveal.headers["cache-control"] == "no-store"
    assert first_reveal.json()["api_key"] == api_key
    assert second_reveal.json()["api_key"] == api_key

    missing_csrf = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={"Origin": "http://testserver"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"]["error"] == "CSRF_REQUIRED"

    wrong_origin = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={
            "Origin": "https://evil.example.com",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["detail"]["error"] == "FORBIDDEN"

    disabled_update = client.patch(
        f"/admin/callers/{caller_id}",
        json={"disabled": True},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert disabled_update.status_code == 200

    disabled_reveal = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert disabled_reveal.status_code == 200
    assert disabled_reveal.json()["api_key"] == api_key
    assert disabled_reveal.json()["disabled"] is True

    with pytest.raises(MCPError):
        resolve_principal(f"Bearer {api_key}")


def test_admin_reveal_expired_caller_key_but_public_auth_rejects(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token
    expires_at = (datetime.now() - timedelta(days=1)).isoformat()

    create_response = client.post(
        "/admin/callers",
        json={"name": "expired-demo", "expires_at": expires_at},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert create_response.status_code == 200
    caller_id = create_response.json()["caller_id"]
    api_key = create_response.json()["api_key"]

    reveal = client.post(
        f"/admin/callers/{caller_id}/reveal-key",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert reveal.status_code == 200
    assert reveal.json()["api_key"] == api_key
    assert reveal.json()["expires_at"] == expires_at
    with pytest.raises(MCPError):
        resolve_principal(f"Bearer {api_key}")


def test_admin_write_accepts_forwarded_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_ADMIN_TRUST_PROXY_HEADERS", "true")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "https://ocr.example.com",
            "Host": "127.0.0.1:8000",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "ocr.example.com",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"]


def test_admin_write_rejects_untrusted_forwarded_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "https://evil.example.com",
            "Host": "127.0.0.1:8000",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "ocr.example.com",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "Cross-origin admin request blocked"


def test_admin_write_does_not_crash_when_proxy_headers_missing(tmp_path, monkeypatch):
    """Regression: trust_proxy_headers=true but the proxy sent no X-Forwarded-*
    headers must fall back to the request's own scheme/host, not crash with
    AttributeError (observed as 500 on POST /api/admin/* behind frp)."""
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_ADMIN_TRUST_PROXY_HEADERS", "true")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"]


def test_admin_write_accepts_foreign_origin_when_same_origin_check_disabled(tmp_path, monkeypatch):
    """MINERU_ADMIN_SAME_ORIGIN_CHECK=false fully bypasses origin checks while
    the CSRF token check still applies."""
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_ADMIN_SAME_ORIGIN_CHECK", "false")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "https://anything.example.com",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"]

    # CSRF token is still mandatory even with the origin check disabled.
    response = client.post(
        "/admin/callers",
        json={"name": "demo2"},
        headers={"Origin": "https://anything.example.com"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "CSRF_REQUIRED"


def test_admin_write_rejects_forwarded_origin_when_proxy_headers_not_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "https://ocr.example.com",
            "Host": "127.0.0.1:8000",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "ocr.example.com",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "Cross-origin admin request blocked"


def test_public_api_allows_cross_origin_response_header(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "*")
    init_default_admin()

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/api/health", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_public_api_auth_failure_includes_cors_for_allowed_origin(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "https://app.example.com")

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/api/stats", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_public_api_auth_failure_does_not_echo_disallowed_origin(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "https://app.example.com")

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/api/stats", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


def test_public_api_auth_failure_without_origin_has_no_cors_header(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "https://app.example.com")

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/api/stats")

    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


def test_public_api_invalid_disabled_and_expired_keys_include_allowed_cors(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "https://app.example.com")
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _create_test_caller(db, "active", "active-token")
    _create_test_caller(db, "disabled", "disabled-token", disabled=True)
    _create_test_caller(
        db,
        "expired",
        "expired-token",
        expires_at=(datetime.now() - timedelta(days=1)).isoformat(),
    )

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))

    for token in ("wrong-token", "disabled-token", "expired-token"):
        response = client.get(
            "/api/stats",
            headers={
                "Origin": "https://app.example.com",
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 401
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_root_health_does_not_emit_cors_allow_origin(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "*")
    init_default_admin()

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/health", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_admin_api_does_not_emit_cors_allow_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "*")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token

    response = client.post(
        "/admin/callers",
        json={"name": "demo"},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_admin_task_creation_validates_before_creating_task(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/tasks",
        data={"backend": "hybrid-http-client", "lang": "ch"},
        files={"file": ("malware.exe", b"MZ fake exe", "application/octet-stream")},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 400
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    assert db.fetch_all("SELECT * FROM tasks") == []


def test_init_default_admin_creates_admin_for_empty_database(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()

    reloaded_admin_auth = importlib.reload(admin_auth_module)

    reloaded_admin_auth.init_default_admin()

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    admin = db.get_admin("admin")
    assert admin is not None
    assert reloaded_admin_auth.verify_password("Admin123!", admin["password_hash"])
    assert admin["must_change_password"] == 0


def test_init_default_admin_keeps_existing_admin_password(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    reset_config()

    reloaded_admin_auth = importlib.reload(admin_auth_module)
    reloaded_admin_auth.init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    original_admin = db.get_admin("admin")
    assert original_admin is not None
    original_hash = original_admin["password_hash"]

    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Changed456!")
    reloaded_admin_auth = importlib.reload(admin_auth_module)
    reloaded_admin_auth.init_default_admin()

    updated_admin = db.get_admin("admin")
    assert updated_admin is not None
    assert updated_admin["password_hash"] == original_hash
    assert reloaded_admin_auth.verify_password("Admin123!", updated_admin["password_hash"])
    assert not reloaded_admin_auth.verify_password("Changed456!", updated_admin["password_hash"])
