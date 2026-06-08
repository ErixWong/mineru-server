import asyncio
from pathlib import Path

from mineru_mcp.config import reset_config
from mineru_mcp.server import create_mcp_server
from mineru_mcp.task_queue import FileManager, TaskDatabase


def _prepare_completed_task(output_root: Path, task_id: str = "task-mcp-results"):
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
    output_files["middle_json"].write_text('{"pdf_info": []}\n', encoding="utf-8")
    output_files["content_list"].write_text('[]\n', encoding="utf-8")
    output_files["content_list_v2"].write_text('[]\n', encoding="utf-8")
    output_files["model_json"].write_text('[]\n', encoding="utf-8")
    (output_files["images_dir"] / "figure-1.png").write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")
    return create_mcp_server()


def test_mcp_get_image_deliverables_includes_items_and_references(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    server = _prepare_completed_task(tmp_path)

    tool = server._tool_manager._tools["get_image_deliverables"]
    payload = asyncio.run(tool.fn(task_id="task-mcp-results"))

    assert payload["status"] == "completed"
    assert payload["count"] == 1
    assert set(payload["images"].keys()) == {"figure-1.png"}
    assert payload["items"][0]["filename"] == "figure-1.png"
    assert payload["items"][0]["referenced_in_markdown"] is True
    assert payload["items"][0]["references"][0]["markdown_path"] == "images/figure-1.png"


def test_mcp_list_deliverables_includes_images_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    server = _prepare_completed_task(tmp_path)

    tool = server._tool_manager._tools["list_deliverables"]
    payload = asyncio.run(tool.fn(task_id="task-mcp-results"))

    artifacts = {item["name"]: item for item in payload["artifacts"]}
    assert payload["status"] == "completed"
    assert artifacts["images"]["role"] == "supplementary"
    assert artifacts["images"]["available"] is True
    assert len(artifacts["images"]["children"]) == 1


def test_mcp_download_deliverable_reports_encoding_and_rejects_unexposed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    reset_config()
    server = _prepare_completed_task(tmp_path)

    hidden_file = tmp_path / "2026" / "06" / "07" / "task-mcp-results" / "internal-debug.log"
    hidden_file.write_text("secret", encoding="utf-8")

    list_tool = server._tool_manager._tools["list_deliverables"]
    artifacts_payload = asyncio.run(list_tool.fn(task_id="task-mcp-results"))
    artifacts = {item["name"]: item for item in artifacts_payload["artifacts"]}

    download_tool = server._tool_manager._tools["download_deliverable"]
    markdown_payload = asyncio.run(
        download_tool.fn(
            task_id="task-mcp-results",
            download_key=artifacts["markdown"]["download_key"],
        )
    )
    assert markdown_payload["encoding"] == "utf-8"

    hidden_payload = asyncio.run(
        download_tool.fn(task_id="task-mcp-results", download_key="internal-debug.log")
    )
    assert hidden_payload["status"] == "error"
    assert "not exposed" in hidden_payload["error"]
