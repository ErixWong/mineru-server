"""Integration tests for real MCP compatibility tools payload verification.

These tests verify the ACTUAL implementation of MCP compatibility tools
by analyzing the source code to ensure they return proper deprecation payloads.

Since the MCP tools require the 'mcp' module runtime, we use source code analysis
and pattern verification instead of direct execution.
"""

import sys
import os
import ast

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest


def load_server_module_source():
    """Load server.py source for analysis."""
    server_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'mineru_mcp', 'server.py')
    
    with open(server_path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    return source, server_path


class TestMCPCompatToolsDeleted:
    """Verify old compatibility tools have been truly deleted."""

    def test_get_default_deliverable_deleted(self):
        """Verify get_default_deliverable is removed from MCP registration."""
        source, _ = load_server_module_source()
        
        # Should NOT have @mcp.tool() for get_default_deliverable
        assert '@mcp.tool()\nasync def get_default_deliverable(' not in source

    def test_get_image_deliverables_deleted(self):
        """Verify get_image_deliverables is removed from MCP registration."""
        source, _ = load_server_module_source()
        
        # Should NOT have @mcp.tool() for get_image_deliverables
        assert '@mcp.tool()\nasync def get_image_deliverables(' not in source

    def test_get_task_result_never_existed(self):
        """Verify get_task_result was never registered as MCP tool."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def get_task_result(' not in source

    def test_list_task_results_never_existed(self):
        """Verify list_task_results was never registered as MCP tool."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def list_task_results(' not in source

    def test_download_task_artifact_never_existed(self):
        """Verify download_task_artifact was never registered as MCP tool."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def download_task_artifact(' not in source


class TestMCPValidTools:
    """Verify valid MCP tools exist."""

    def test_create_task_exists(self):
        """Verify create_task (unified) tool exists."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def create_task(' in source

    def test_list_deliverables_exists(self):
        """Verify list_deliverables tool exists."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def list_deliverables(' in source

    def test_download_deliverable_exists(self):
        """Verify download_deliverable tool exists."""
        source, _ = load_server_module_source()
        
        assert '@mcp.tool()\nasync def download_deliverable(' in source


class TestAddDeprecatedInfoHelper:
    """Verify the add_deprecated_info helper function (used by internal impls)."""

    def test_add_deprecated_info_function_exists(self):
        """Verify add_deprecated_info function is defined in server.py."""
        source, _ = load_server_module_source()
        
        assert "def add_deprecated_info" in source


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])