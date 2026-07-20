import importlib

from fastapi.testclient import TestClient

import mineru_mcp.admin_auth as admin_auth_module
from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password, verify_password
from mineru_mcp.admin_console import inject_common_js, render_page
from mineru_mcp.api import create_api_app
from mineru_mcp.app import create_unified_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase


def _login_admin(client: TestClient):
    response = client.post(
        "/admin/login",
        json={"username": "admin", "password": get_default_admin_password()},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response


def test_render_page_accepts_common_js_template():
    page = render_page("test", inject_common_js("<script>{COMMON_JS_HELPERS}</script>"))
    assert "function escapeHtml" in page
    assert "<script>" in page


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
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "*")
    reset_config()
    init_default_admin()

    client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    response = client.get("/api/health", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_root_health_does_not_emit_cors_allow_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    monkeypatch.setenv("MINERU_CORS_ORIGINS", "*")
    reset_config()
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
