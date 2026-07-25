from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import reset_task_service
from mineru_mcp.task_queue import TaskDatabase, FileManager


def _reset_runtime_config() -> None:
    reset_config()
    reset_task_service()


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id="image-route-user",
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name="Image Route User",
        caller_id="image-route-user",
    )


def _prepare_completed_task(output_root: Path, task_id: str = "task-images") -> tuple[TaskDatabase, FileManager]:
    db = TaskDatabase(db_path=str(output_root / "tasks.db"))
    file_manager = FileManager(output_root=str(output_root))

    task_dir = output_root / "2026" / "06" / "07" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "document.pdf").write_bytes(b"%PDF-1.4\nmock pdf")

    db.create_task(
        task_id=task_id,
        task_dir=str(task_dir),
        input_filename="document.pdf",
        backend="vlm-http-client",
        owner_id="image-route-user",
        owner_type="api_key",
        caller_id="image-route-user",
    )
    db.update_status(task_id, "completed")

    output_files = file_manager.get_output_files(task_dir, "document.pdf", "vlm-http-client")
    output_files["images_dir"].mkdir(parents=True, exist_ok=True)
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text(
        "Intro text\n\n![Figure 1](images/figure-1.png)\n\nTail text\n",
        encoding="utf-8",
    )
    output_files["middle_json"].write_text('{"pdf_info": []}\n', encoding="utf-8")
    output_files["content_list"].write_text('[]\n', encoding="utf-8")
    output_files["content_list_v2"].write_text('[]\n', encoding="utf-8")
    output_files["model_json"].write_text('[]\n', encoding="utf-8")
    (output_files["images_dir"] / "figure-1.png").write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    (output_files["images_dir"] / "extra.jpg").write_bytes(b"\xff\xd8\xfffake-jpeg")

    return db, file_manager


def test_task_deliverables_include_image_files(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/tasks/task-images/deliverables")

    assert response.status_code == 200
    payload = response.json()
    artifacts = {item["name"]: item for item in payload["artifacts"]}
    assert payload["status"] == "completed"
    assert artifacts["images/figure-1.png"]["role"] == "supplementary"
    assert artifacts["images/figure-1.png"]["artifact_type"] == "image_file"
    assert artifacts["images/figure-1.png"]["download_key"].endswith("document/vlm/images/figure-1.png")
    assert artifacts["images/extra.jpg"]["media_type"] == "image/jpeg"


def test_task_image_file_serves_binary_content(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/tasks/task-images/deliverables/images/figure-1.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_task_image_route_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/tasks/task-images/deliverables/images/%2E%2E%2Ftasks.db")

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_IMAGE_PATH"


def test_task_result_supports_named_formats_and_artifact_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        artifacts_response = client.get("/tasks/task-images/deliverables")
    assert artifacts_response.status_code == 200
    artifacts_payload = artifacts_response.json()
    artifacts = {item["name"]: item for item in artifacts_payload["artifacts"]}
    assert artifacts["markdown"]["role"] == "primary"
    assert artifacts["markdown"]["is_default"] is True
    assert artifacts["markdown"]["downloadable"] is True
    assert artifacts["markdown"]["download_key"].endswith("document/vlm/document.md")
    assert artifacts["content_list_v2"]["role"] == "experimental"
    assert artifacts["model_json"]["available"] is True
    assert artifacts["images/figure-1.png"]["downloadable"] is True
    assert artifacts["images/extra.jpg"]["downloadable"] is True


def test_task_artifact_download_uses_unified_download_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        artifacts_response = client.get("/tasks/task-images/deliverables")
    artifacts = {item["name"]: item for item in artifacts_response.json()["artifacts"]}

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        markdown_download = client.get(
            "/tasks/task-images/deliverables/download",
            params={"download_key": artifacts["markdown"]["download_key"]},
        )
    assert markdown_download.status_code == 200
    assert markdown_download.headers["content-type"].startswith("text/markdown")
    assert "Figure 1" in markdown_download.text

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        image_download = client.get(
            "/tasks/task-images/deliverables/download",
            params={"download_key": artifacts["images/figure-1.png"]["download_key"]},
        )
    assert image_download.status_code == 200
    assert image_download.headers["content-type"] == "image/png"
    assert image_download.content.startswith(b"\x89PNG")


def test_task_artifact_download_rejects_invalid_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get(
            "/tasks/task-images/deliverables/download",
            params={"download_key": "../tasks.db"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_DOWNLOAD_KEY"


def test_task_artifact_download_rejects_unexposed_task_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    _reset_runtime_config()
    _prepare_completed_task(tmp_path)

    hidden_file = tmp_path / "2026" / "06" / "07" / "task-images" / "internal-debug.log"
    hidden_file.write_text("secret", encoding="utf-8")

    client = TestClient(create_api_app())
    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get(
            "/tasks/task-images/deliverables/download",
            params={"download_key": "internal-debug.log"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ARTIFACT_NOT_AVAILABLE"
