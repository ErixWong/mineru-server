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
        "create_task",  # NEW: Unified task creation
        "get_task_status",
        "list_deliverables",
        "download_deliverable",
        "cancel_task",
    }
    
    # Auxiliary tools
    auxiliary_tools = {
        "list_tasks",
        "list_postprocess_rules",
        "run_postprocess",
        "list_postprocess_runs",
    }
    
    # Deleted tools (truly removed from MCP registration):
    # - get_default_deliverable: was returning removed signal, now actually deleted
    # - get_image_deliverables: was returning removed signal, now actually deleted
    # - create_task_from_file: internal impl only, never was an MCP tool
    # - create_task_from_upload: internal impl only, never was an MCP tool
    # - get_task_result: never existed as MCP tool
    # - list_task_results: never existed as MCP tool
    # - download_task_artifact: never existed as MCP tool
    # - get_task_images: never existed as MCP tool
    # - list_parsing_backends: never existed as MCP tool
    # - list_supported_file_formats: never existed as MCP tool
    
    all_expected_tools = main_tools | auxiliary_tools
    
    assert tool_names == all_expected_tools, f"Tool names mismatch: {tool_names - all_expected_tools} unexpected, {all_expected_tools - tool_names} missing"

    # Verify main tools are present
    assert main_tools.issubset(tool_names), f"Missing main tools: {main_tools - tool_names}"

    # Negative assertions - these should NOT exist
    assert "get_default_deliverable" not in tool_names, "get_default_deliverable should be deleted"
    assert "get_image_deliverables" not in tool_names, "get_image_deliverables should be deleted"
    assert "create_task_from_file" not in tool_names
    assert "create_task_from_upload" not in tool_names
    assert "get_task_result" not in tool_names
    assert "list_task_results" not in tool_names
    assert "download_task_artifact" not in tool_names
    assert "get_task_images" not in tool_names
    assert "list_parsing_backends" not in tool_names
    assert "list_supported_file_formats" not in tool_names
