import importlib
import io
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mineru_mcp.admin_auth as admin_auth_module
import mineru_mcp.admin_api as admin_api_module
import mineru_mcp.app as app_module
from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password, verify_password
from mineru_mcp.api import create_api_app
from mineru_mcp.app import create_unified_app
from mineru_mcp.auth import resolve_principal
from mineru_mcp.config import get_config, reset_config
from mineru_mcp.services.config_service import ConfigService, load_effective_config
from mineru_mcp.errors import MCPError
from mineru_mcp.task_queue import TaskDatabase
from mineru_mcp.task_queue import FileManager


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


def test_admin_dashboard_returns_metrics_without_sensitive_caller_fields(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    db.create_caller(
        caller_id="caller-a",
        name="Caller A",
        api_key="secret-token-a",
        api_key_prefix="secr",
        api_key_suffix="en-a",
    )
    db.create_task(
        task_id="task-completed",
        task_dir=str(tmp_path / "task-completed"),
        input_filename="ok.pdf",
        backend="pipeline",
        owner_id="caller-a",
        owner_type="api_key",
        caller_id="caller-a",
    )
    db.update_status("task-completed", "processing")
    db.update_status("task-completed", "completed")
    db.create_task(
        task_id="task-failed",
        task_dir=str(tmp_path / "task-failed"),
        input_filename="bad.pdf",
        backend="pipeline",
        owner_id="caller-a",
        owner_type="api_key",
        caller_id="caller-a",
    )
    db.update_status("task-failed", "failed", error="parse failed")

    client = TestClient(create_api_app())
    _login_admin(client)

    response = client.get("/admin/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue"]["completed"] == 1
    assert payload["queue"]["failed"] == 1
    assert payload["callers"]["total"] == 1
    assert payload["recent_failed_tasks"][0]["task_id"] == "task-failed"
    serialized = str(payload)
    assert "secret-token-a" not in serialized
    assert "api_key_hash" not in serialized
    assert "api_key_encrypted" not in serialized


def test_admin_diagnostics_reports_structured_checks(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_DEFAULT_BACKEND", "hybrid-http-client")
    monkeypatch.delenv("MINERU_VL_SERVER", raising=False)
    monkeypatch.delenv("MINERU_VL_API_KEY", raising=False)
    monkeypatch.delenv("MINERU_VL_MODEL_NAME", raising=False)
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    _login_admin(client)

    response = client.get("/admin/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "critical"
    checks = {item["key"]: item for item in payload["checks"]}
    assert checks["vlm_config"]["status"] == "failed"
    assert checks["caller_key_master_key"]["status"] == "ok"
    serialized = str(payload)
    assert TEST_CALLER_KEY_MASTER_KEY not in serialized


def test_system_config_service_applies_db_overrides_and_decrypts_secrets(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_DEFAULT_BACKEND", "pipeline")
    monkeypatch.setenv("MINERU_VL_API_KEY", "env-vlm-key")
    reset_config()

    db_path = str(tmp_path / "tasks.db")
    service = ConfigService(db_path, TEST_CALLER_KEY_MASTER_KEY)
    service.update_runtime_settings(
        settings={
            "default_backend": "hybrid-http-client",
            "vlm_base_url": "https://db.example/v1",
            "vlm_model": "db-model",
            "task_timeout": 42,
            "retry_limit": 5,
            "cleanup_days": 90,
        },
        secrets={"vlm_api_key": "db-vlm-secret"},
        updated_by="test-admin",
    )

    reset_config()
    config = get_config()

    assert config.default_backend == "hybrid-http-client"
    assert config.vlm_base_url == "https://db.example/v1"
    assert config.vlm_model == "db-model"
    assert config.vlm_api_key == "db-vlm-secret"
    assert config.task_timeout == 42
    assert config.retry_limit == 5
    assert config.cleanup_days == 90

    db = TaskDatabase(db_path=db_path)
    secret_row = db.list_system_secrets(include_ciphertext=True)["vlm_api_key"]
    assert secret_row["secret_encrypted"] != "db-vlm-secret"
    assert secret_row["secret_prefix"] == "db-vlm"
    assert secret_row["secret_suffix"] == "cret"


def test_system_config_secret_decrypt_failure_does_not_fall_back_to_env(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.delenv("MINERU_CALLER_KEY_MASTER_KEY", raising=False)
    reset_config()

    db_path = str(tmp_path / "tasks.db")
    service = ConfigService(db_path, TEST_CALLER_KEY_MASTER_KEY)
    service.update_runtime_settings(
        settings={},
        secrets={"vlm_api_key": "db-vlm-secret"},
        updated_by="test-admin",
    )

    from mineru_mcp.config import MCPConfig

    bootstrap = MCPConfig.from_env()
    bootstrap.caller_key_master_key = None

    with pytest.raises(RuntimeError, match="MINERU_VL_API_KEY is stored in database"):
        load_effective_config(bootstrap)


def test_admin_runtime_settings_update_persists_db_values_without_revealing_secrets(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.patch(
        "/admin/settings/runtime",
        json={
            "default_backend": "pipeline",
            "vlm_base_url": "https://vlm.example/v1",
            "vlm_model": "vlm-model",
            "vlm_api_key": "secret-vlm-token",
            "title_base_url": "https://title.example/v1",
            "title_model": "title-model",
            "title_api_key": "secret-title-token",
            "task_timeout": 123,
            "retry_limit": 4,
            "cleanup_days": 45,
            "max_concurrent": 2,
        },
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["default_backend"] == "pipeline"
    assert payload["config"]["vlm_base_url"] == "https://vlm.example/v1"
    assert payload["config"]["task_timeout"] == 123
    assert payload["sources"]["default_backend"] == "database"
    assert payload["secrets"]["vlm_api_key"]["configured"] is True
    assert payload["secrets"]["vlm_api_key"]["source"] == "database"
    serialized = str(payload)
    assert "secret-vlm-token" not in serialized
    assert "secret-title-token" not in serialized

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    secrets = db.list_system_secrets(include_ciphertext=True)
    assert secrets["vlm_api_key"]["secret_encrypted"] != "secret-vlm-token"
    assert secrets["title_api_key"]["secret_encrypted"] != "secret-title-token"


def test_admin_restart_disabled_by_default(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/system/restart",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "RESTART_DISABLED"


def test_admin_restart_unavailable_without_uvicorn_server(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_ADMIN_ALLOW_RESTART", "true")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/system/restart",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "RESTART_UNAVAILABLE"


def test_admin_restart_rejects_active_work(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_ADMIN_ALLOW_RESTART", "true")
    reset_config()
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    db.create_task(
        task_id="task-running",
        task_dir=str(tmp_path / "task-running"),
        input_filename="running.pdf",
        backend="pipeline",
    )
    db.update_status("task-running", "processing")
    scheduler_state = {"paused": False, "resumed": False}

    class FakeScheduler:
        def pause_fetching(self):
            scheduler_state["paused"] = True

        def resume_fetching(self):
            scheduler_state["resumed"] = True

    monkeypatch.setattr(app_module, "is_restart_available", lambda: True)
    monkeypatch.setattr(app_module, "get_task_scheduler", lambda: FakeScheduler())

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/system/restart",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 409
    payload = response.json()["detail"]
    assert payload["error"] == "RESTART_BUSY"
    assert payload["processing_tasks"] == 1
    assert scheduler_state == {"paused": True, "resumed": True}


def test_admin_restart_schedules_graceful_shutdown(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_ADMIN_ALLOW_RESTART", "true")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    called = {"scheduled": False}
    scheduler_state = {"paused": False, "resumed": False}

    class FakeScheduler:
        def pause_fetching(self):
            scheduler_state["paused"] = True

        def resume_fetching(self):
            scheduler_state["resumed"] = True

    async def fake_request_server_restart():
        called["scheduled"] = True

    monkeypatch.setattr(app_module, "is_restart_available", lambda: True)
    monkeypatch.setattr(app_module, "is_restart_requested", lambda: False)
    monkeypatch.setattr(app_module, "get_task_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(app_module, "request_server_restart", fake_request_server_restart)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/system/restart",
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 202
    assert response.json()["restart"] == "scheduled"
    assert called["scheduled"] is True
    assert scheduler_state == {"paused": True, "resumed": False}


def test_admin_restart_resumes_fetching_after_unexpected_error(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    monkeypatch.setenv("MINERU_ADMIN_ALLOW_RESTART", "true")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    scheduler_state = {"paused": False, "resumed": False}

    class FakeScheduler:
        def pause_fetching(self):
            scheduler_state["paused"] = True

        def resume_fetching(self):
            scheduler_state["resumed"] = True

    def fail_get_db():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app_module, "is_restart_available", lambda: True)
    monkeypatch.setattr(app_module, "get_task_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(admin_api_module, "_get_db", fail_get_db)

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    with pytest.raises(RuntimeError, match="database unavailable"):
        client.post(
            "/admin/system/restart",
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": csrf_token,
            },
        )

    assert scheduler_state == {"paused": True, "resumed": True}


def test_admin_task_list_supports_product_filters(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    db.create_caller(
        caller_id="caller-a",
        name="Caller A",
        api_key="secret-token-a",
        api_key_prefix="secr",
        api_key_suffix="en-a",
    )
    db.create_task(
        task_id="task-contract",
        task_dir=str(tmp_path / "task-contract"),
        input_filename="contract.pdf",
        backend="pipeline",
        owner_id="caller-a",
        owner_type="api_key",
        caller_id="caller-a",
        enable_postprocess=True,
        postprocess_status="pending",
    )
    db.create_postprocess_run(
        run_id="run-contract",
        task_id="task-contract",
        plan_id="plan-a",
        plan_title_snapshot="Plan A",
        steps_snapshot=[{"action_id": "action-a", "name": "Action A"}],
    )
    db.create_task(
        task_id="task-invoice",
        task_dir=str(tmp_path / "task-invoice"),
        input_filename="invoice.pdf",
        backend="hybrid-http-client",
        owner_id="admin-console",
        owner_type="single_user",
    )
    db.update_status("task-invoice", "processing")
    old_started = (datetime.now() - timedelta(minutes=40)).isoformat()
    db.execute(
        "UPDATE tasks SET started_at = ?, updated_at = ? WHERE task_id = ?",
        (old_started, old_started, "task-invoice"),
    )

    client = TestClient(create_api_app())
    _login_admin(client)

    filename_response = client.get("/admin/tasks?filename=contract")
    backend_response = client.get("/admin/tasks?backend=hybrid-http-client")
    postprocess_response = client.get("/admin/tasks?postprocess_status=pending")
    stale_response = client.get("/admin/tasks?stale_processing_minutes=30")
    unassigned_response = client.get("/admin/tasks?caller_id=__unassigned__")

    assert filename_response.status_code == 200
    assert [item["task_id"] for item in filename_response.json()["tasks"]] == ["task-contract"]
    assert backend_response.status_code == 200
    assert [item["task_id"] for item in backend_response.json()["tasks"]] == ["task-invoice"]
    assert postprocess_response.status_code == 200
    assert [item["task_id"] for item in postprocess_response.json()["tasks"]] == ["task-contract"]
    assert stale_response.status_code == 200
    assert [item["task_id"] for item in stale_response.json()["tasks"]] == ["task-invoice"]
    assert unassigned_response.status_code == 200
    assert [item["task_id"] for item in unassigned_response.json()["tasks"]] == ["task-invoice"]


def test_admin_task_diagnostics_sanitizes_request_and_reports_outputs(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    task_dir = tmp_path / "2026" / "07" / "25" / "task-diagnostics"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-dia.pdf").write_bytes(b"%PDF-1.4\n")
    db.create_task(
        task_id="task-diagnostics",
        task_dir=str(task_dir),
        input_filename="document.pdf",
        backend="pipeline",
        lang="ch",
        server_url="https://secret.example.com/v1",
        owner_id="admin-console",
        owner_type="single_user",
        enable_postprocess=True,
        postprocess_status="pending",
    )
    db.update_status("task-diagnostics", "processing")
    db.update_status("task-diagnostics", "completed")
    db.add_log("task-diagnostics", "INFO", "parsed")
    db.add_log(
        "task-diagnostics",
        "ERROR",
        "Output: C:\\Users\\Eric\\secret\\out.md api_key=secret-token Authorization: Bearer bearer-token https://secret.example.com/v1?api_key=secret",
    )
    fm = FileManager(output_root=str(tmp_path))
    output_files = fm.get_output_files(task_dir, "task-dia.pdf", "pipeline")
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text("# ok\n", encoding="utf-8")
    output_files["middle_json"].write_text("{}\n", encoding="utf-8")

    client = TestClient(create_api_app())
    _login_admin(client)

    response = client.get("/admin/tasks/task-diagnostics/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["server_url_configured"] is True
    assert "server_url" not in payload["request"]
    assert payload["output_validation"]["required_missing"] == []
    assert payload["logs"][-2]["message"] == "parsed"
    assert "<path>" in payload["logs"][-1]["message"]
    assert "<url>" in payload["logs"][-1]["message"]
    assert "secret.example.com" not in str(payload)
    assert "secret-token" not in str(payload)
    assert "bearer-token" not in str(payload)
    assert "C:\\Users\\Eric" not in str(payload)


def test_admin_deliverables_archive_uses_allowed_artifacts_only(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    task_dir = tmp_path / "2026" / "07" / "25" / "task-archive"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-arc.pdf").write_bytes(b"%PDF-1.4\n")
    db.create_task(
        task_id="task-archive",
        task_dir=str(task_dir),
        input_filename="document.pdf",
        backend="pipeline",
        owner_id="admin-console",
        owner_type="single_user",
    )
    db.update_status("task-archive", "completed")
    fm = FileManager(output_root=str(tmp_path))
    output_files = fm.get_output_files(task_dir, "task-arc.pdf", "pipeline")
    output_files["images_dir"].mkdir(parents=True, exist_ok=True)
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text("# ok\n![one](images/one.png)\n", encoding="utf-8")
    output_files["middle_json"].write_text("{}\n", encoding="utf-8")
    output_files["content_list"].write_text("[]\n", encoding="utf-8")
    (output_files["images_dir"] / "one.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (task_dir / "internal-debug.log").write_text("secret", encoding="utf-8")

    client = TestClient(create_api_app())
    _login_admin(client)
    spool_calls = []
    real_spooled = admin_api_module.tempfile.SpooledTemporaryFile

    def recording_spooled(*args, **kwargs):
        spool_calls.append({"args": args, "kwargs": kwargs})
        return real_spooled(*args, **kwargs)

    monkeypatch.setattr(admin_api_module.tempfile, "SpooledTemporaryFile", recording_spooled)

    response = client.get("/admin/tasks/task-archive/deliverables/archive")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert spool_calls
    assert spool_calls[0]["kwargs"]["max_size"] == 32 * 1024 * 1024
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())

    assert "markdown/document.md" in names
    assert "json/task-arc_middle.json" in names
    assert "json/task-arc_content_list.json" in names
    assert "images/one.png" in names
    assert "internal-debug.log" not in names


def test_admin_clone_task_copies_source_and_allows_overrides(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    _create_test_caller(db, "caller-a", "secret-token-a")
    task_dir = tmp_path / "2026" / "07" / "25" / "task-source"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-sou.pdf").write_bytes(b"%PDF-1.4\nsource")
    (task_dir / "auto").mkdir(parents=True, exist_ok=True)
    (task_dir / "auto" / "old.md").write_text("# old\n", encoding="utf-8")
    db.create_task(
        task_id="task-source",
        task_dir=str(task_dir),
        input_filename="source.pdf",
        backend="vlm-auto-engine",
        lang="en",
        formula_enable=True,
        table_enable=True,
        image_analysis=True,
        start_page_id=0,
        end_page_id=99999,
        owner_id="caller-a",
        owner_type="api_key",
        caller_id="caller-a",
        enable_postprocess=False,
    )
    db.update_status("task-source", "failed", error="parse failed")

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")
    source_pdf = task_dir / "task-sou.pdf"
    original_read_bytes = Path.read_bytes

    def fail_source_read_bytes(path):
        if path == source_pdf:
            raise AssertionError("clone should stream-copy source files")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_source_read_bytes)

    response = client.post(
        "/admin/tasks/task-source/clone",
        json={
            "backend": "pipeline",
            "lang": "ch",
            "formula_enable": False,
            "start_page_id": 1,
            "end_page_id": 2,
            "inherit_caller": False,
        },
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_task_id"] == "task-source"
    assert payload["task_id"] != "task-source"

    cloned = db.get_task(payload["task_id"])
    assert cloned["status"] == "pending"
    assert cloned["backend"] == "pipeline"
    assert cloned["lang"] == "ch"
    assert cloned["formula_enable"] == 0
    assert cloned["table_enable"] == 1
    assert cloned["start_page_id"] == 1
    assert cloned["end_page_id"] == 2
    assert cloned["caller_id"] is None
    cloned_dir = Path(cloned["task_dir"])
    assert cloned_dir.exists()
    copied_inputs = list(cloned_dir.glob("*.pdf"))
    assert len(copied_inputs) == 1
    with copied_inputs[0].open("rb") as copied_file:
        assert copied_file.read() == b"%PDF-1.4\nsource"
    assert not (cloned_dir / "auto" / "old.md").exists()


def test_admin_clone_task_missing_source_returns_404(tmp_path, monkeypatch):
    _set_common_env(tmp_path, monkeypatch)
    init_default_admin()
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.set_admin_password_change_required("admin", False)
    task_dir = tmp_path / "2026" / "07" / "25" / "task-missing-source"
    task_dir.mkdir(parents=True, exist_ok=True)
    db.create_task(
        task_id="task-missing-source",
        task_dir=str(task_dir),
        input_filename="missing.pdf",
        backend="pipeline",
        owner_id="admin-console",
        owner_type="single_user",
    )

    client = TestClient(create_api_app())
    login_response = _login_admin(client)
    csrf_token = login_response.cookies.get("admin_csrf")

    response = client.post(
        "/admin/tasks/task-missing-source/clone",
        json={},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "SOURCE_NOT_FOUND"


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
