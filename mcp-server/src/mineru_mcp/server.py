"""
MCP Server Implementation

FastMCP server that exposes MinerU PDF parsing capabilities via local task queue.
Runs local MinerU-backed parsing tasks instead of proxying to a separate HTTP API.

Response structure aligned with markitdown-server for consistency.
"""

import base64
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from mineru_mcp.config import get_config, MCPConfig
from mineru_mcp.models import TaskStatus
from mineru_mcp.principal import get_current_principal
from mineru_mcp.auth import get_stdio_principal
from mineru_mcp.validation import (
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception
from mineru_mcp.task_queue import TaskDatabase, FileManager, TaskStateService
from mineru_mcp.services import get_task_service


def _get_principal_for_mcp() -> Any:
    """Get the current principal for MCP tool calls.
    
    First tries to get from context variable (set by HTTP layer),
    falls back to default in stdio mode.
    """
    principal = get_current_principal()
    if principal is not None:
        return principal
    
    # Fallback for stdio mode where there's no HTTP layer
    return get_stdio_principal()


def setup_logging(log_level: str = "INFO") -> None:
    """Setup loguru logging."""
    logger.remove()
    logger.add(sys.stderr, level=log_level.upper())


def create_mcp_server(config: Optional[MCPConfig] = None) -> FastMCP:
    """Create the FastMCP server with MinerU tools.
    
    Args:
        config: MCP configuration. Defaults to environment config.
        
    Returns:
        FastMCP server instance.
    """
    if config is None:
        config = get_config()
    
    setup_logging(config.log_level)
    
    logger.info(f"Creating MCP Server: {config.server_name}")
    logger.info(f"Mode: {config.server_mode}")
    logger.info(f"Max Concurrent: {config.max_concurrent}")
    
    mcp = FastMCP(
        config.server_name,
        stateless_http=True if config.is_http_mode() else False,
        json_response=True if config.is_http_mode() else False,
    )
    
    db = TaskDatabase(db_path=config.db_path)
    file_manager = FileManager(output_root=config.output_root)

    def _find_artifact_by_download_key(items: list[dict[str, Any]], download_key: str) -> dict[str, Any] | None:
        """Find an artifact anywhere in the deliverables tree."""
        for item in items:
            if item.get("download_key") == download_key:
                return item

            children = item.get("children")
            if isinstance(children, list):
                found = _find_artifact_by_download_key(children, download_key)
                if found is not None:
                    return found

        return None
    
    @mcp.tool()
    async def create_task(
        file_base64: Optional[str] = None,
        file_name: Optional[str] = None,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        enable_postprocess: Optional[bool] = None,
        postprocess_rule_id: Optional[str] = None,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Create an asynchronous parsing task from file content.

        This is the unified task creation tool. Provide file_base64.

        Args:
            file_base64: Base64-encoded PDF file content.
            file_name: Optional file name for display and extension detection (used with file_base64).
            backend: Parsing backend (defaults to config.default_backend).
            lang: Document language for OCR (ch, en, korean, japan, etc.).
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            image_analysis: Enable VLM image analysis (generates AI descriptions).
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).
            enable_postprocess: Optional override. None means inherit caller default, False disables postprocess for this task.
            postprocess_rule_id: Optional postprocess rule ID. The caller default rule is inherited only when both
                enable_postprocess and postprocess_rule_id are omitted. Passing enable_postprocess=True without a
                rule ID raises a validation error.

        Returns:
            Task submission result:
                - task_id: Unique task identifier
                - status: "submitted" (or "error" on failure)
                - created_at: Task creation timestamp (ISO format)
                - error: Error message (if status is "error")
        """
        if ctx:
            await ctx.info(f"Creating task: file_base64={bool(file_base64)}")

        try:
            # Get current principal for ownership
            principal = _get_principal_for_mcp()
            
            # Use shared TaskService for task creation
            task_service = get_task_service()
            result = task_service.create_task_from_base64(
                file_base64=file_base64,
                file_name=file_name,
                backend=backend,
                lang=lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                server_url=server_url,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                enable_postprocess=enable_postprocess,
                postprocess_rule_id=postprocess_rule_id,
                principal=principal,
            )
            return result

        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            return {
                "task_id": "",
                "status": "error",
                "error": e.message,
            }
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            return {
                "task_id": "",
                "status": "error",
                "error": str(e),
            }

    @mcp.tool()
    async def list_postprocess_rules(
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """List enabled postprocess rules available to task creation."""
        if ctx:
            await ctx.info("Listing postprocess rules")

        rules = db.list_postprocess_rules(include_disabled=False)
        return {
            "items": [
                {
                    "rule_id": rule["rule_id"],
                    "title": rule["title"],
                    "output_filename": rule["output_filename"],
                }
                for rule in rules
            ]
        }

    @mcp.tool()
    async def get_task_status(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get the current status of a parsing task.

        Checks task progress until the task reaches a terminal state.
        Call repeatedly until status is "completed" or "failed".

        Args:
            task_id: The task ID returned by create_task.

        Returns:
            Task status information:
                - pending/processing: task_id, status, progress, message, created_at, updated_at
                - completed: task_id, status, progress, message, created_at, updated_at, completed_at
                - failed/cancelled: task_id, status, progress, message, error, updated_at, completed_at
                - not_found: task_id, status="not_found", error (also for unauthorized access)
        """
        if ctx:
            await ctx.debug(f"Checking task: {task_id}")

        # Get current principal for authorization
        principal = _get_principal_for_mcp()
        
        # Use shared TaskService with authorization
        task_service = get_task_service()
        return task_service.get_task_status_authorized(task_id, principal)

    @mcp.tool()
    async def list_deliverables(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """List logical result artifacts available for a completed task."""
        if ctx:
            await ctx.info(f"Listing artifacts for task: {task_id}")

        # Get current principal for authorization
        principal = _get_principal_for_mcp()
        
        # Use shared TaskService with authorization
        task_service = get_task_service()
        return task_service.list_deliverables_authorized(task_id, principal)

    @mcp.tool()
    async def download_deliverable(
        task_id: str,
        download_key: str,
        include_content: bool = True,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Download one artifact through the unified artifact-first contract.

        Args:
            task_id: The task ID.
            download_key: The artifact download key from list_deliverables.
            include_content: If False, returns only metadata without the actual content.
                            For large images, set to False to get lightweight response.

        Returns:
            Artifact metadata and optionally content.
        """
        if ctx:
            await ctx.info(f"Downloading artifact for task: {task_id}")

        # Get current principal for authorization
        principal = _get_principal_for_mcp()
        
        # Use shared TaskService with authorization
        task_service = get_task_service()
        return task_service.download_deliverable_authorized(task_id, download_key, include_content, principal)

    @mcp.tool()
    async def cancel_task(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> bool:
        """Cancel a pending or processing task.

        Args:
            task_id: The task ID to cancel.

        Returns:
            True if task was cancelled, False otherwise.
        """
        if ctx:
            await ctx.info(f"Cancelling task: {task_id}")

        try:
            # Get current principal for authorization
            principal = _get_principal_for_mcp()
            
            # Use TaskService with authorization check
            task_service = get_task_service()
            result = task_service.cancel_task_authorized(task_id, principal)
            
            if not result.get("cancelled", False) and result.get("error"):
                # Task not found or not authorized
                return False
            
            # If task is processing, also cancel via scheduler
            task = db.get_task(task_id)
            if task and task.get('status') == 'processing':
                from mineru_mcp.app import _task_scheduler
                if _task_scheduler:
                    _task_scheduler.processor.cancel_task(task_id)
            
            return result.get("cancelled", False)

        except Exception as e:
            logger.error(f"Cancel task error: {e}")
            return False

    @mcp.tool()
    async def list_tasks(
        status: str = "",
        limit: int = 10,
        ctx: Context[ServerSession, None] = None,
    ) -> list[dict[str, Any]]:
        """List tasks with optional status filter.
        
        Only returns tasks owned by the current principal.
        Admins can see all tasks via the admin_list_tasks tool.
        
        Args:
            status: Filter by status (optional).
            limit: Maximum number of tasks to return (default 10).
            
        Returns:
            List of task dictionaries with task_id, filename, status, progress, timestamps.
        """
        if ctx:
            await ctx.debug(f"Listing tasks: status={status}, limit={limit}")
        
        try:
            # Get current principal for authorization
            principal = _get_principal_for_mcp()
            
            # Use TaskService with owner filtering
            task_service = get_task_service()
            tasks = task_service.get_tasks_for_principal(principal, status=status, limit=limit)
            
            return tasks
            
        except Exception as e:
            logger.error(f"List tasks error: {e}")
            return []
    
    return mcp


_server: Optional[FastMCP] = None


def get_server() -> FastMCP:
    """Get the global MCP server instance."""
    if _server is None:
        _server = create_mcp_server()
    return _server


def reset_server() -> None:
    """Reset the global server (for testing)."""
    global _server
    _server = None
