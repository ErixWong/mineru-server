from fastapi.testclient import TestClient

from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password
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
