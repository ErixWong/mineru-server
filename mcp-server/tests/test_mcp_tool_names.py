from mineru_mcp.config import reset_config
from mineru_mcp.server import create_mcp_server


def test_mcp_tool_names_are_explicit_and_consistent(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "output" / "tasks.db"))
    reset_config()

    server = create_mcp_server()
    tool_names = set(server._tool_manager._tools.keys())

    # Main tools (recommended for use)
    main_tools = {
        "create_task",  # NEW: Unified task creation (replaces create_task_from_file and create_task_from_upload)
        "get_task_status",
        "get_default_deliverable",
        "list_deliverables",
        "download_deliverable",
        "cancel_task",
    }
    
    # Deprecated/legacy tools (still available for backward compatibility)
    deprecated_tools = {
        "create_task_from_file",  # [DEPRECATED] Use create_task instead
        "create_task_from_upload",  # [DEPRECATED] Use create_task instead
        "get_task_result",  # [DEPRECATED] Use get_default_deliverable instead
        "list_task_results",  # [DEPRECATED] Use list_deliverables instead
        "download_task_artifact",  # [DEPRECATED] Use download_deliverable instead
        "get_task_images",  # [DEPRECATED] Use list_deliverables + download_deliverable instead
        "get_image_deliverables",  # [DEPRECATED] Use list_deliverables + download_deliverable instead
        "list_parsing_backends",  # [DEPRECATED] Static info - use /api/backends instead
        "list_supported_file_formats",  # [DEPRECATED] Static info - use docs instead
    }
    
    # Auxiliary tools
    auxiliary_tools = {
        "list_tasks",
    }
    
    all_expected_tools = main_tools | deprecated_tools | auxiliary_tools
    
    assert tool_names == all_expected_tools, f"Tool names mismatch: {tool_names - all_expected_tools} unexpected, {all_expected_tools - tool_names} missing"

    # Verify main tools are present
    assert main_tools.issubset(tool_names), f"Missing main tools: {main_tools - tool_names}"
    
    # Verify deprecated tools are marked (by presence)
    assert deprecated_tools.issubset(tool_names), f"Missing deprecated tools: {deprecated_tools - tool_names}"

    # Negative assertions (these should NOT be in the tool set)
    assert "submit_task" not in tool_names
    assert "submit_uploaded_task" not in tool_names
    assert "get_task" not in tool_names
    assert "get_images" not in tool_names
    assert "list_backends" not in tool_names
    assert "get_supported_formats" not in tool_names
