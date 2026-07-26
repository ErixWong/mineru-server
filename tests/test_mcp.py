"""
Tests for MinerU MCP Server Module

Unit tests for validation, errors, config, and server components.
"""

import pytest
from pathlib import Path
import os
import shutil
import tempfile

from fastapi.testclient import TestClient

# Test imports
from mineru_mcp.validation import (
    validate_file_path,
    validate_task_id,
    validate_backend,
    resolve_backend_options,
    validate_language,
    validate_page_range,
    ValidationError,
    ERROR_FILE_NOT_FOUND,
    ERROR_INVALID_EXTENSION,
    ERROR_OUTSIDE_ALLOWED_DIRS,
    ERROR_FILE_TOO_LARGE,
    ERROR_INVALID_TASK_ID,
    ERROR_INVALID_BACKEND,
    ERROR_INVALID_BACKEND_OPTIONS,
    ERROR_INVALID_PAGE_RANGE,
)

from mineru_mcp.errors import (
    MCPError,
    ErrorCode,
    from_exception,
    file_not_found,
    task_not_found,
    invalid_backend,
)

from mineru_mcp.config import MCPConfig, reset_config


class TestValidation:
    """Tests for input validation functions."""
    
    def test_validate_task_id_valid(self):
        """Test valid task ID formats."""
        # UUID format
        assert validate_task_id("abc123-def456-ghi789") == "abc123-def456-ghi789"
        
        # Simple alphanumeric
        assert validate_task_id("task123") == "task123"
        
        # With underscores
        assert validate_task_id("task_123_abc") == "task_123_abc"
    
    def test_validate_task_id_empty(self):
        """Test empty task ID raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_task_id("")
        
        assert exc_info.value.code == ERROR_INVALID_TASK_ID
    
    def test_validate_task_id_invalid_chars(self):
        """Test task ID with invalid characters raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_task_id("task@123")
        
        assert exc_info.value.code == ERROR_INVALID_TASK_ID
    
    def test_validate_task_id_too_long(self):
        """Test task ID too long raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_task_id("a" * 100)
        
        assert exc_info.value.code == ERROR_INVALID_TASK_ID
    
    def test_validate_backend_valid(self):
        """Test valid backend names."""
        valid_backends = [
            "pipeline",
            "vlm-auto-engine",
            "vlm-http-client",
            "hybrid-auto-engine",
            "hybrid-http-client",
        ]
        
        for backend in valid_backends:
            assert validate_backend(backend) == backend
    
    def test_validate_backend_invalid(self):
        """Test invalid backend name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_backend("invalid-backend")
        
        assert exc_info.value.code == ERROR_INVALID_BACKEND

    def test_resolve_backend_options_requires_server_url_for_http_backend(self):
        with pytest.raises(ValidationError) as exc_info:
            resolve_backend_options("hybrid-http-client", None)

        assert exc_info.value.code == ERROR_INVALID_BACKEND_OPTIONS

    def test_resolve_backend_options_rejects_server_url_for_local_backend(self):
        with pytest.raises(ValidationError) as exc_info:
            resolve_backend_options("hybrid-auto-engine", "http://localhost:30000/v1")

        assert exc_info.value.code == ERROR_INVALID_BACKEND_OPTIONS

    def test_resolve_backend_options_normalizes_http_backend(self):
        backend, server_url = resolve_backend_options(
            "vlm-http-client",
            "  http://localhost:30000/v1  ",
        )

        assert backend == "vlm-http-client"
        assert server_url == "http://localhost:30000/v1"
    
    def test_validate_language_valid(self):
        """Test valid language codes."""
        assert validate_language("ch") == "ch"
        assert validate_language("en") == "en"
        assert validate_language("EN") == "en"  # Case insensitive
    
    def test_validate_page_range_valid(self):
        """Test valid page ranges."""
        start, end = validate_page_range(0, 10)
        assert start == 0
        assert end == 10
        
        start, end = validate_page_range(5, 5)
        assert start == 5
        assert end == 5
    
    def test_validate_page_range_negative_start(self):
        """Test negative start page raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_page_range(-1, 10)
        
        assert exc_info.value.code == ERROR_INVALID_PAGE_RANGE
    
    def test_validate_page_range_end_before_start(self):
        """Test end page before start page raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_page_range(10, 5)
        
        assert exc_info.value.code == ERROR_INVALID_PAGE_RANGE
    
    def test_validate_page_range_too_large(self):
        """Test page range too large raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_page_range(0, 100000)
        
        assert exc_info.value.code == ERROR_INVALID_PAGE_RANGE
    
    def test_validate_file_path_not_exists(self):
        """Test non-existent file raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_path("/nonexistent/file.pdf")
        
        assert exc_info.value.code == ERROR_FILE_NOT_FOUND
    
    def test_validate_file_path_invalid_extension(self):
        """Test invalid file extension raises error."""
        # Create a temp file with wrong extension
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError) as exc_info:
                validate_file_path(temp_path, allowed_dirs=[Path(temp_path).parent])
            
            assert exc_info.value.code == ERROR_INVALID_EXTENSION
        finally:
            os.unlink(temp_path)
    
    def test_validate_file_path_outside_allowed_dirs(self):
        """Test file outside allowed directories raises error."""
        # Create a temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            # Set allowed dirs to a different directory
            with pytest.raises(ValidationError) as exc_info:
                validate_file_path(temp_path, allowed_dirs=[Path("/tmp/other")])
            
            assert exc_info.value.code == ERROR_OUTSIDE_ALLOWED_DIRS
        finally:
            os.unlink(temp_path)


class TestErrors:
    """Tests for error handling functions."""
    
    def test_mcp_error_to_dict(self):
        """Test MCPError serialization."""
        error = MCPError(
            code=ErrorCode.FILE_NOT_FOUND,
            message="File not found",
            details={"path": "/test/file.pdf"},
            http_status=404,
        )
        
        result = error.to_dict()
        
        assert result["status"] == "error"
        assert result["error"] == "FILE_NOT_FOUND"
        assert result["message"] == "File not found"
        assert "file.pdf" in result["detail"]["path"]
    
    def test_mcp_error_sanitize_sensitive_keys(self):
        """Test MCPError sanitizes sensitive keys."""
        error = MCPError(
            code=ErrorCode.AUTH_INVALID,
            message="Auth invalid",
            details={"api_key": "secret123", "token": "token123", "safe_key": "safe_value"},
            http_status=401,
        )
        
        result = error.to_dict()
        
        assert "api_key" not in result.get("detail", {})
        assert "token" not in result.get("detail", {})
        assert "safe_key" in result.get("detail", {})
    
    def test_from_exception_validation_error(self):
        """Test converting ValidationError to MCPError."""
        validation_error = ValidationError(
            code=ERROR_FILE_NOT_FOUND,
            message="File not found",
            details={"path": "/test/file.pdf"},
        )
        
        mcp_error = from_exception(validation_error)
        
        assert mcp_error.code == ErrorCode.FILE_NOT_FOUND
        assert mcp_error.message == "File not found"
    
    def test_from_exception_file_not_found(self):
        """Test converting FileNotFoundError to MCPError."""
        error = FileNotFoundError("File not found: /test/file.pdf")
        
        mcp_error = from_exception(error)
        
        assert mcp_error.code == ErrorCode.FILE_NOT_FOUND
    
    def test_from_exception_value_error(self):
        """Test converting ValueError to MCPError."""
        error = ValueError("Invalid value")
        
        mcp_error = from_exception(error)
        
        assert mcp_error.code == ErrorCode.INVALID_PARAMETER
    
    def test_from_exception_timeout_error(self):
        """Test converting TimeoutError to MCPError."""
        error = TimeoutError("Operation timed out")
        
        mcp_error = from_exception(error)
        
        assert mcp_error.code == ErrorCode.TASK_TIMEOUT
    
    def test_predefined_errors(self):
        """Test predefined error functions."""
        error = file_not_found("/test/file.pdf")
        assert error.code == ErrorCode.FILE_NOT_FOUND
        assert error.http_status == 404
        
        error = task_not_found("task-123")
        assert error.code == ErrorCode.TASK_NOT_FOUND
        assert error.http_status == 404
        
        error = invalid_backend("invalid", ["pipeline", "vlm-http-client"])
        assert error.code == ErrorCode.INVALID_BACKEND
        assert error.http_status == 400


class TestConfig:
    """Tests for configuration management."""
    
    def test_config_from_env_defaults(self):
        """Test default configuration values."""
        os.environ.pop("MCP_SERVER_MODE", None)
        reset_config()

        config = MCPConfig.from_env()

        assert config.server_mode == "stdio"
        assert config.http_port == 8002
        assert config.vlm_base_url is None
    
    def test_config_from_env_custom(self):
        """Test custom configuration from environment."""
        os.environ["MINERU_VL_SERVER"] = "http://custom:9000"
        os.environ["MCP_SERVER_MODE"] = "http"
        os.environ["MCP_HTTP_PORT"] = "9001"
        reset_config()

        config = MCPConfig.from_env()

        assert config.vlm_base_url == "http://custom:9000"
        assert config.server_mode == "http"
        assert config.http_port == 9001

        os.environ.pop("MINERU_VL_SERVER", None)
        os.environ.pop("MCP_SERVER_MODE", None)
        os.environ.pop("MCP_HTTP_PORT", None)
        reset_config()
    
    def test_config_is_http_mode(self):
        """Test HTTP mode detection."""
        os.environ["MCP_SERVER_MODE"] = "http"
        reset_config()
        config = MCPConfig.from_env()
        assert config.is_http_mode() is True
        assert config.is_stdio_mode() is False
        os.environ.pop("MCP_SERVER_MODE", None)
        reset_config()
    
    def test_config_is_stdio_mode(self):
        """Test stdio mode detection."""
        os.environ["MCP_SERVER_MODE"] = "stdio"
        reset_config()
        config = MCPConfig.from_env()
        assert config.is_stdio_mode() is True
        assert config.is_http_mode() is False
        os.environ.pop("MCP_SERVER_MODE", None)
        reset_config()

    def test_get_config_does_not_write_mineru_tools_config(self):
        """Title env vars stay in MCPConfig and should not create mineru.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mineru.json"
            os.environ["MINERU_TOOLS_CONFIG_JSON"] = str(config_path)
            os.environ["MINERU_TITLE_API_KEY"] = "title-key"
            os.environ["MINERU_TITLE_BASE_URL"] = "https://title.example/v1"
            os.environ["MINERU_TITLE_MODEL"] = "title-model"
            reset_config()

            try:
                get_config = __import__("mineru_mcp.config", fromlist=["get_config"]).get_config
                config = get_config()

                assert config.title_api_key == "title-key"
                assert config.title_base_url == "https://title.example/v1"
                assert config.title_model == "title-model"
                assert config_path.exists() is False
            finally:
                os.environ.pop("MINERU_TOOLS_CONFIG_JSON", None)
                os.environ.pop("MINERU_TITLE_API_KEY", None)
                os.environ.pop("MINERU_TITLE_BASE_URL", None)
                os.environ.pop("MINERU_TITLE_MODEL", None)
                reset_config()


class TestMinerUClient:
    """Tests for MinerU HTTP client (module removed — tests skipped)."""
    
    @pytest.mark.skip(reason="mineru_mcp.mineru_client module has been removed")
    def test_client_initialization(self):
        """Test client initialization."""
        from mineru_mcp.mineru_client import MinerUClient
        
        client = MinerUClient(base_url="http://custom:9000")
        
        assert client.base_url == "http://custom:9000"
        assert client.timeout is not None
    
    @pytest.mark.skip(reason="mineru_mcp.mineru_client module has been removed")
    def test_client_list_backends(self):
        """Test list_backends returns expected backends."""
        from mineru_mcp.mineru_client import MinerUClient

        client = MinerUClient()

        backends = {
            "pipeline",
            "vlm-auto-engine",
            "vlm-http-client",
            "hybrid-auto-engine",
            "hybrid-http-client",
        }

        assert backends == {
            "pipeline",
            "vlm-auto-engine",
            "vlm-http-client",
            "hybrid-auto-engine",
            "hybrid-http-client",
        }


class TestServerTools:
    """Tests for MCP server tool registration."""

    def test_expected_tools_registered(self):
        """Verify current explicit MCP tools are registered."""
        from mineru_mcp.server import create_mcp_server, reset_server
        from mineru_mcp.config import reset_config

        os.environ.pop("MCP_SERVER_MODE", None)
        os.environ["MCP_SERVER_MODE"] = "stdio"

        try:
            reset_config()
            reset_server()
            mcp = create_mcp_server()
            tools = list(mcp._tool_manager.list_tools())
            tool_names = [t.name for t in tools]

            expected = [
                "create_task",
                "get_task_status",
                "list_postprocess_rules",
                "list_deliverables",
                "download_deliverable",
                "cancel_task",
                "list_tasks",
            ]
            for name in expected:
                assert name in tool_names, f"Missing tool: {name}"

            assert "create_task_from_file" not in tool_names
            assert "create_task_from_upload" not in tool_names
            assert "get_default_deliverable" not in tool_names
            assert "get_image_deliverables" not in tool_names
            assert "get_task_result" not in tool_names
            assert "list_task_results" not in tool_names
            assert "download_task_artifact" not in tool_names
            assert "get_task_images" not in tool_names
            assert "list_parsing_backends" not in tool_names
            assert "list_supported_file_formats" not in tool_names
            assert "parse_pdf" not in tool_names
            assert "health_check" not in tool_names
            assert "submit_task" not in tool_names
            assert "get_task" not in tool_names
            assert "get_images" not in tool_names
        finally:
            reset_config()
            reset_server()
            os.environ.pop("MCP_SERVER_MODE", None)


class TestUnifiedApp:
    """Tests for the unified Starlette app."""

    TEST_CALLER_KEY_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

    @staticmethod
    def _mcp_initialize_payload() -> dict:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        }

    def _set_test_master_key(self):
        os.environ["MINERU_CALLER_KEY_MASTER_KEY"] = self.TEST_CALLER_KEY_MASTER_KEY

    @staticmethod
    def _clear_test_master_key():
        os.environ.pop("MINERU_CALLER_KEY_MASTER_KEY", None)

    def test_create_unified_app_api_only(self):
        """Verify app can be created with API only."""
        os.environ["MCP_SERVER_MODE"] = "http"
        self._set_test_master_key()
        try:
            reset_config()
            from mineru_mcp.app import create_unified_app
            from mineru_mcp.server import reset_server
            app = create_unified_app(enable_api=True, enable_mcp=False)
            route_paths = [r.path for r in app.routes if hasattr(r, "path")]
            assert "/" in route_paths
            assert "/health" in route_paths
        finally:
            reset_config()
            reset_server()
            os.environ.pop("MCP_SERVER_MODE", None)
            self._clear_test_master_key()

    def test_create_unified_app_mcp_only(self):
        """Verify app can be created with MCP only."""
        os.environ["MCP_SERVER_MODE"] = "http"
        self._set_test_master_key()
        try:
            reset_config()
            from mineru_mcp.app import create_unified_app
            from mineru_mcp.server import reset_server
            app = create_unified_app(enable_api=False, enable_mcp=True)
            route_paths = [r.path for r in app.routes if hasattr(r, "path")]
            assert "/mcp/sse" in route_paths
        finally:
            reset_config()
            reset_server()
            os.environ.pop("MCP_SERVER_MODE", None)
            self._clear_test_master_key()

    def test_create_unified_app_both(self):
        """Verify app can be created with both API and MCP."""
        os.environ["MCP_SERVER_MODE"] = "http"
        self._set_test_master_key()
        try:
            reset_config()
            from mineru_mcp.app import create_unified_app
            from mineru_mcp.server import reset_server
            app = create_unified_app(enable_api=True, enable_mcp=True)
            route_paths = [r.path for r in app.routes if hasattr(r, "path")]
            assert "/" in route_paths
            assert "/mcp/sse" in route_paths
        finally:
            reset_config()
            reset_server()
            os.environ.pop("MCP_SERVER_MODE", None)
            self._clear_test_master_key()

    def test_create_unified_app_requires_caller_key_master_key(self):
        """Service startup must fail fast when caller key master key is missing."""
        os.environ["MCP_SERVER_MODE"] = "http"
        self._clear_test_master_key()
        try:
            reset_config()
            from mineru_mcp.app import create_unified_app

            with pytest.raises(RuntimeError, match="MINERU_CALLER_KEY_MASTER_KEY is required"):
                create_unified_app(enable_api=True, enable_mcp=False)
        finally:
            reset_config()
            os.environ.pop("MCP_SERVER_MODE", None)

    def test_mcp_http_accepts_both_slash_forms_without_redirect(self):
        """Verify /mcp and /mcp/ both serve MCP directly without redirect."""
        os.environ["MCP_SERVER_MODE"] = "http"
        self._set_test_master_key()
        temp_dir = tempfile.mkdtemp()
        os.environ["MINERU_OUTPUT_ROOT"] = temp_dir
        os.environ["MINERU_DB_PATH"] = str(Path(temp_dir) / "tasks.db")
        try:
            reset_config()
            from mineru_mcp.auth import reset_auth_config
            from mineru_mcp.app import create_unified_app
            from mineru_mcp.server import reset_server
            from mineru_mcp.task_queue import TaskDatabase

            reset_auth_config()
            db = TaskDatabase(db_path=os.environ["MINERU_DB_PATH"])
            db.create_caller(
                caller_id="test-mcp-http",
                name="Test MCP HTTP",
                api_key="test-token-123456",
                api_key_prefix="test",
                api_key_suffix="3456",
            )

            app = create_unified_app(enable_api=False, enable_mcp=True)
            headers = {
                "Authorization": "Bearer test-token-123456",
                "Accept": "application/json, text/event-stream",
            }

            with TestClient(app) as client:
                response_without_slash = client.post(
                    "/mcp",
                    json=self._mcp_initialize_payload(),
                    headers=headers,
                    follow_redirects=False,
                )
                response_with_slash = client.post(
                    "/mcp/",
                    json=self._mcp_initialize_payload(),
                    headers=headers,
                    follow_redirects=False,
                )

                assert response_without_slash.status_code == 200
                assert response_with_slash.status_code == 200
                assert response_without_slash.headers.get("location") is None
                assert response_with_slash.headers.get("location") is None
                assert response_without_slash.json()["result"]["serverInfo"]["name"] == "MinerU MCP Server"
                assert response_with_slash.json()["result"]["serverInfo"]["name"] == "MinerU MCP Server"
        finally:
            reset_config()
            reset_server()
            os.environ.pop("MCP_SERVER_MODE", None)
            self._clear_test_master_key()
            os.environ.pop("MINERU_OUTPUT_ROOT", None)
            os.environ.pop("MINERU_DB_PATH", None)
            shutil.rmtree(temp_dir, ignore_errors=True)


# Run tests with: pytest src/mineru/mcp/tests/test_mcp.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
