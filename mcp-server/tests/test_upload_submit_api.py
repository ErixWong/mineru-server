from fastapi.testclient import TestClient
from unittest.mock import patch

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import reset_task_service
from mineru_mcp.task_queue import TaskDatabase


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id="test-user",
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name="Test User",
        caller_id="test-user",
    )


def test_submit_task_returns_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_VL_SERVER", "http://configured-vlm:30000/v1")
    reset_config()
    reset_task_service()

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(
            "/tasks",
            data={
                "backend": "hybrid-http-client",
                "lang": "ch",
                "formula_enable": "true",
                "table_enable": "true",
                "image_analysis": "true",
            },
            files={
                "file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"task_id", "message", "created_at"}
    assert payload["task_id"]

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task = db.get_task(payload["task_id"])
    assert task is not None
    assert task["input_filename"] == "sample.pdf"

    assert db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='uploads'") == []


def test_submit_task_validates_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(
            "/tasks",
            data={"backend": "not-a-backend"},
            files={
                "file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf"),
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_BACKEND"

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    assert db.fetch_all("SELECT * FROM tasks") == []


def test_submit_task_requires_server_url_for_http_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.delenv("MINERU_VL_SERVER", raising=False)
    monkeypatch.setenv("MINERU_DEFAULT_BACKEND", "hybrid-http-client")
    reset_config()
    reset_task_service()

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(
            "/tasks",
            data={"backend": "hybrid-http-client"},
            files={
                "file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf"),
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_BACKEND_OPTIONS"


def test_submit_task_rejects_server_url_for_local_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    reset_task_service()

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(
            "/tasks",
            data={
                "backend": "hybrid-auto-engine",
                "server_url": "http://localhost:30000/v1",
            },
            files={
                "file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf"),
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_BACKEND_OPTIONS"
