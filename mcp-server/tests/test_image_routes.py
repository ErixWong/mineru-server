from pathlib import Path

from fastapi.testclient import TestClient

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase, FileManager


def _prepare_completed_task(output_root: Path, task_id: str = "task-images") -> tuple[TaskDatabase, FileManager]:
    db = TaskDatabase(db_path=str(output_root / "tasks.db"))
    file_manager = FileManager(output_root=str(output_root))

    task_dir = output_root / "2026" / "06" / "07" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    db.create_task(
        task_id=task_id,
        task_dir=str(task_dir),
        input_filename="document.pdf",
        backend="vlm-http-client",
    )
    db.update_status(task_id, "completed")

    output_files = file_manager.get_output_files(task_dir, "document.pdf", "vlm-http-client")
    output_files["images_dir"].mkdir(parents=True, exist_ok=True)
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text(
        "Intro text\n\n![Figure 1](images/figure-1.png)\n\nTail text\n",
        encoding="utf-8",
    )
    (output_files["images_dir"] / "figure-1.png").write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    (output_files["images_dir"] / "extra.jpg").write_bytes(b"\xff\xd8\xfffake-jpeg")

    return db, file_manager


def test_task_images_returns_static_urls_and_markdown_references(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    response = client.get("/tasks/task-images/images")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert set(payload["images"].keys()) == {"figure-1.png", "extra.jpg"}

    items = {item["filename"]: item for item in payload["items"]}
    assert items["figure-1.png"]["url"].endswith("/tasks/task-images/images/figure-1.png")
    assert items["figure-1.png"]["referenced_in_markdown"] is True
    assert items["figure-1.png"]["references"][0]["markdown_path"] == "images/figure-1.png"
    assert items["figure-1.png"]["references"][0]["line_number"] == 3
    assert items["extra.jpg"]["referenced_in_markdown"] is False
    assert items["extra.jpg"]["references"] == []


def test_task_image_file_serves_binary_content(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    response = client.get("/tasks/task-images/images/figure-1.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_task_image_route_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    response = client.get("/tasks/task-images/images/%2E%2E%2Ftasks.db")

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_IMAGE_PATH"
