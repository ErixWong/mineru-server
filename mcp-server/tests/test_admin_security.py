import importlib

from fastapi.testclient import TestClient

import mineru_mcp.admin_auth as admin_auth_module
from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password, verify_password
from mineru_mcp.admin_console import inject_common_js, render_page
from mineru_mcp.api import create_api_app
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
