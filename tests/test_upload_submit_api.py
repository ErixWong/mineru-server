import io

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import reset_task_service
from mineru_mcp.task_queue import TaskDatabase
from mineru_mcp.utils import save_upload_stream
from mineru_mcp.validation import ValidationError


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id="test-user",
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name="Test User",
        caller_id="test-user",
    )


def _seed_task(
    db: TaskDatabase,
    tmp_path,
    task_id: str,
    owner_id: str,
    status: str,
    created_at: str,
) -> None:
    db.create_task(
        task_id=task_id,
        task_dir=str(tmp_path / task_id),
        input_filename=f"{task_id}.pdf",
        backend="pipeline",
        owner_id=owner_id,
        owner_type="api_key",
        caller_id=owner_id,
    )
    db.update_status(task_id, status=status, progress=100 if status == "completed" else 0)
    db.execute(
        "UPDATE tasks SET created_at = ?, updated_at = ? WHERE task_id = ?",
        (created_at, created_at, task_id),
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


def test_submit_task_uses_streamed_temp_file_and_cleans_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    reset_task_service()

    payload = b"%PDF-1.4\nstreamed upload"
    captured = {}

    class RecordingTaskService:
        def create_task_from_file(self, **kwargs):
            source_path = kwargs["source_path"]
            captured["source_path"] = source_path
            assert source_path.exists()
            assert source_path.read_bytes() == payload
            return {
                "task_id": "task-streamed",
                "status": "submitted",
                "created_at": "2026-08-04T00:00:00",
            }

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_task_service", return_value=RecordingTaskService()), patch(
        "mineru_mcp.api.get_principal_from_request", return_value=_principal()
    ):
        response = client.post(
            "/tasks",
            files={"file": ("streamed.pdf", payload, "application/pdf")},
        )

    assert response.status_code == 200
    assert not captured["source_path"].exists()


def test_save_upload_stream_rejects_oversized_file():
    with pytest.raises(ValidationError) as error:
        save_upload_stream(io.BytesIO(b"12345"), "sample.pdf", max_size=4)

    assert error.value.code == "FILE_TOO_LARGE"


def test_list_tasks_returns_paginated_current_caller_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    reset_task_service()

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_task(db, tmp_path, "task-a-old", "test-user", "pending", "2026-01-01T00:00:00")
    _seed_task(db, tmp_path, "task-a-mid", "test-user", "completed", "2026-01-02T00:00:00")
    _seed_task(db, tmp_path, "task-a-new", "test-user", "failed", "2026-01-03T00:00:00")
    _seed_task(db, tmp_path, "task-b-newer", "other-user", "completed", "2026-01-04T00:00:00")

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        page_one = client.get("/tasks", params={"page": 1, "size": 2})
        page_two = client.get("/tasks", params={"page": 2, "size": 2})
        completed = client.get("/tasks", params={"status": "completed", "page": 1, "size": 10})

    assert page_one.status_code == 200
    assert page_one.json()["total"] == 3
    assert page_one.json()["total_pages"] == 2
    assert [item["task_id"] for item in page_one.json()["tasks"]] == ["task-a-new", "task-a-mid"]

    assert page_two.status_code == 200
    assert [item["task_id"] for item in page_two.json()["tasks"]] == ["task-a-old"]

    assert completed.status_code == 200
    assert completed.json()["total"] == 1
    assert [item["task_id"] for item in completed.json()["tasks"]] == ["task-a-mid"]


def test_list_tasks_rejects_invalid_status(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    reset_task_service()

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/tasks", params={"status": "unknown"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_STATUS"


def test_stats_returns_current_caller_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    reset_task_service()

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_task(db, tmp_path, "task-a-pending", "test-user", "pending", "2026-01-01T00:00:00")
    _seed_task(db, tmp_path, "task-a-completed", "test-user", "completed", "2026-01-02T00:00:00")
    _seed_task(db, tmp_path, "task-b-completed", "other-user", "completed", "2026-01-03T00:00:00")

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["queue_stats"]["pending"] == 1
    assert payload["queue_stats"]["completed"] == 1


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
