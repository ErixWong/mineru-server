from fastapi.testclient import TestClient

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase


def test_upload_submit_returns_task_id_without_exposing_upload_id(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()

    client = TestClient(create_api_app())
    response = client.post(
        "/uploads/submit",
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

    uploads = db.fetch_all("SELECT * FROM uploads")
    assert len(uploads) == 1
    assert uploads[0]["status"] == "consumed"


def test_upload_submit_validates_backend_before_staging(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()

    client = TestClient(create_api_app())
    response = client.post(
        "/uploads/submit",
        data={"backend": "not-a-backend"},
        files={
            "file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_BACKEND"

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    assert db.fetch_all("SELECT * FROM uploads") == []
    assert db.fetch_all("SELECT * FROM tasks") == []
