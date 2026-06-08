from mineru_mcp.config import reset_config
from mineru_mcp.server import create_mcp_server


def test_mcp_tool_names_are_explicit_and_consistent(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "output" / "tasks.db"))
    reset_config()

    server = create_mcp_server()
    tool_names = set(server._tool_manager._tools.keys())

    assert tool_names == {
        "create_task_from_file",
        "create_task_from_upload",
        "get_task_status",
        "get_default_deliverable",
        "list_deliverables",
        "download_deliverable",
        "get_image_deliverables",
        "get_task_result",
        "list_task_results",
        "download_task_artifact",
        "get_task_images",
        "cancel_task",
        "list_tasks",
        "list_parsing_backends",
        "list_supported_file_formats",
    }

    assert "submit_task" not in tool_names
    assert "submit_uploaded_task" not in tool_names
    assert "get_task" not in tool_names
    assert "get_images" not in tool_names
    assert "list_backends" not in tool_names
    assert "get_supported_formats" not in tool_names
