"""
MinerU MCP Server Module

This module provides a Model Context Protocol (MCP) server that exposes
MinerU's PDF parsing capabilities to MCP clients (Claude Desktop, Cline, etc.).

The server runs in two modes:
- stdio: For desktop MCP clients (Claude Desktop, Cline)
- streamable-http: For remote HTTP calls

Usage:
    # stdio mode (for Claude Desktop)
    mineru-mcp
    
    # HTTP mode (for remote calls)
    mineru-mcp --mode http --port 8001
    
    # Generate auth token
    python -m mineru_mcp.auth

Components:
    - config: Configuration management via environment variables
    - validation: Input validation (file paths, task IDs, backends)
    - errors: Structured error handling with error codes
    - auth: Bearer Token authentication for HTTP mode
    - concurrency: Rate limiting and concurrent task control
    - server: FastMCP server implementation
    - cli: Command-line interface
"""

__version__ = "0.2.0"

from mineru_mcp.config import (
    MCPConfig,
    get_config,
    reset_config,
    DEFAULT_BACKEND,
    VALID_BACKENDS,
)

from mineru_mcp.validation import (
    ValidationError,
    validate_file_path,
    validate_task_id,
    validate_backend,
    validate_language,
    validate_page_range,
    get_allowed_dirs,
)

from mineru_mcp.errors import (
    ErrorCode,
    MCPError,
    from_exception,
    file_not_found,
    path_traversal,
    file_too_large,
    invalid_extension,
    task_not_found,
    task_failed,
    task_timeout,
    task_still_processing,
    invalid_backend,
    auth_missing,
    auth_invalid,
    internal_error,
    unknown_error,
)

from mineru_mcp.auth import (
    get_auth_token,
    is_auth_required,
    validate_token,
    check_auth_header,
    generate_token,
)

from mineru_mcp.concurrency import (
    RateLimitConfig,
    RateLimiter,
    ConcurrentTaskLimiter,
    ConcurrencyManager,
    get_concurrency_manager,
    reset_concurrency_manager,
)

from mineru_mcp.server import (
    create_mcp_server,
    get_server,
    reset_server,
)

from mineru_mcp.api import create_api_app

from mineru_mcp.app import create_unified_app, run_unified_server

from mineru_mcp.models import (
    TaskStatus,
    UploadStatus,
    HealthResponse,
    SubmitTaskResponse,
    UploadResponse,
    SubmitUploadedTaskRequest,
    TaskDetailResponse,
    TaskStatusResponse,
    TaskResultResponse,
    TaskArtifactItem,
    TaskArtifactsResponse,
    TaskImageReference,
    TaskImageItem,
    TaskImagesResponse,
    CancelTaskResponse,
    BackendsResponse,
    BackendInfo,
    ErrorResponse,
    QueueStatsResponse,
    QueueStatsWrapper,
)

__all__ = [
    # Version
    "__version__",
    # Config
    "MCPConfig",
    "get_config",
    "reset_config",
    "DEFAULT_BACKEND",
    "VALID_BACKENDS",
    # Validation
    "ValidationError",
    "validate_file_path",
    "validate_task_id",
    "validate_backend",
    "validate_language",
    "validate_page_range",
    "get_allowed_dirs",
    # Errors
    "ErrorCode",
    "MCPError",
    "from_exception",
    "file_not_found",
    "path_traversal",
    "file_too_large",
    "invalid_extension",
    "task_not_found",
    "task_failed",
    "task_timeout",
    "task_still_processing",
    "invalid_backend",
    "auth_missing",
    "auth_invalid",
    "internal_error",
    "unknown_error",
    # Auth
    "get_auth_token",
    "is_auth_required",
    "validate_token",
    "check_auth_header",
    "generate_token",
    # Concurrency
    "RateLimitConfig",
    "RateLimiter",
    "ConcurrentTaskLimiter",
    "ConcurrencyManager",
    "get_concurrency_manager",
    "reset_concurrency_manager",
    # Server
    "create_mcp_server",
    "get_server",
    "reset_server",
    # API
    "create_api_app",
    # Unified App
    "create_unified_app",
    "run_unified_server",
    # Models
    "TaskStatus",
    "UploadStatus",
    "HealthResponse",
    "SubmitTaskResponse",
    "UploadResponse",
    "SubmitUploadedTaskRequest",
    "TaskDetailResponse",
    "TaskStatusResponse",
    "TaskResultResponse",
    "TaskArtifactItem",
    "TaskArtifactsResponse",
    "TaskImageReference",
    "TaskImageItem",
    "TaskImagesResponse",
    "CancelTaskResponse",
    "BackendsResponse",
    "BackendInfo",
    "ErrorResponse",
    "QueueStatsResponse",
    "QueueStatsWrapper",
]
