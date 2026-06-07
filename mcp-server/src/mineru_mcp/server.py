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
from mineru_mcp.validation import (
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception, task_not_found
from mineru_mcp.task_queue import TaskDatabase, FileManager, TaskStateService


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
    
    @mcp.tool()
    async def create_task_from_file(
        file_base64: str,
        file_name: Optional[str] = None,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Create an asynchronous parsing task from file content.
        
        This tool creates a task and returns immediately with a task ID.
        Use get_task_status to poll progress and get_task_result when ready.
        
        Args:
            file_base64: Base64-encoded PDF file content (required).
            file_name: Optional file name for display and extension detection.
            backend: Parsing backend (defaults to config.default_backend).
            lang: Document language for OCR (ch, en, korean, japan, etc.).
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            image_analysis: Enable VLM image analysis (generates AI descriptions).
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).
            
        Returns:
            Task submission result aligned with markitdown-server:
                - task_id: Unique task identifier
                - status: "submitted" (or "error" on failure)
                - created_at: Task creation timestamp (ISO format)
                - error: Error message (if status is "error")
        """
        if ctx:
            await ctx.info(f"Submitting task for: {file_name or 'unnamed'}")
        
        try:
            effective_backend = backend if backend is not None else config.default_backend
            effective_server_url = server_url if server_url is not None else config.get_vlm_server_url()
            
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            logger.info(f"Decoding base64 file: {file_name or 'unnamed'}")
            
            from mineru_mcp.validation import MAX_FILE_SIZE, ERROR_FILE_TOO_LARGE, ValidationError
            
            file_bytes = base64.b64decode(file_base64)
            
            if len(file_bytes) > MAX_FILE_SIZE:
                raise ValidationError(
                    ERROR_FILE_TOO_LARGE,
                    f"File size ({len(file_bytes)} bytes) exceeds maximum ({MAX_FILE_SIZE} bytes)",
                    {"size": len(file_bytes), "max_size": MAX_FILE_SIZE},
                )
            
            task_id, task_dir = file_manager.create_task_dir()
            
            input_filename = f"input{Path(file_name).suffix if file_name else '.pdf'}"
            input_path = task_dir / input_filename
            input_path.write_bytes(file_bytes)
            
            db.create_task(
                task_id=task_id,
                task_dir=str(task_dir),
                input_filename=input_filename,
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                server_url=effective_server_url,
                timeout_seconds=config.task_timeout,
            )
            
            task = db.get_task(task_id)
            created_at = task['created_at'] if task else datetime.now().isoformat()
            
            if ctx:
                await ctx.info(f"Task submitted: {task_id}")
            
            logger.info(f"Task {task_id} submitted to queue")
            
            return {
                "task_id": task_id,
                "status": "submitted",
                "created_at": created_at,
            }
            
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
    async def create_task_from_upload(
        upload_id: str,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Create a parsing task from a previously uploaded file."""
        if ctx:
            await ctx.info(f"Submitting uploaded file: {upload_id}")

        try:
            upload = db.get_upload(upload_id)
            if upload is None:
                return {
                    "task_id": "",
                    "status": "error",
                    "error": "Upload not found",
                }

            if upload["status"] != "uploaded":
                return {
                    "task_id": "",
                    "status": "error",
                    "error": f"Upload status is '{upload['status']}', expected 'uploaded'",
                }

            effective_backend = backend if backend is not None else config.default_backend
            effective_server_url = server_url if server_url is not None else config.get_vlm_server_url()

            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)

            source_path = Path(upload["file_path"])
            if not source_path.exists():
                return {
                    "task_id": "",
                    "status": "error",
                    "error": "Uploaded file is missing",
                }

            if not db.consume_upload(upload_id):
                return {
                    "task_id": "",
                    "status": "error",
                    "error": "Upload has already been consumed",
                }

            try:
                task_id, task_dir = file_manager.create_task_dir()
                input_filename = Path(upload["file_name"]).name
                input_path = task_dir / input_filename
                input_path.write_bytes(source_path.read_bytes())

                db.create_task(
                    task_id=task_id,
                    task_dir=str(task_dir),
                    input_filename=input_filename,
                    backend=validated_backend,
                    lang=validated_lang,
                    formula_enable=formula_enable,
                    table_enable=table_enable,
                    image_analysis=image_analysis,
                    start_page_id=start_page_id,
                    end_page_id=end_page_id,
                    server_url=effective_server_url,
                    timeout_seconds=config.task_timeout,
                )
            except Exception:
                db.release_upload(upload_id)
                raise

            task = db.get_task(task_id)
            created_at = task["created_at"] if task else datetime.now().isoformat()

            return {
                "task_id": task_id,
                "status": "submitted",
                "created_at": created_at,
            }

        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            return {
                "task_id": "",
                "status": "error",
                "error": e.message,
            }
        except Exception as e:
            logger.error(f"Submit uploaded task error: {e}")
            return {
                "task_id": "",
                "status": "error",
                "error": str(e),
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
            task_id: The task ID returned by create_task_from_file or create_task_from_upload.

        Returns:
            Task status information:
                - pending/processing: task_id, status, progress, message, created_at, updated_at
                - completed: task_id, status, progress, message, created_at, updated_at, completed_at
                - failed/cancelled: task_id, status, progress, message, error, updated_at, completed_at
                - not_found: task_id, status="not_found", error
        """
        if ctx:
            await ctx.debug(f"Checking task: {task_id}")

        try:
            task = db.get_task(task_id)
            
            base = {
                "task_id": task_id,
                "created_at": task['created_at'] if task else None,
            }
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return {
                    **base,
                    "status": "not_found",
                    "error": f"Task '{task_id}' not found",
                }
            
            status = task['status']
            progress = task.get('progress', 0)
            message = task.get('message', f"Task is {status}")
            updated_at = task.get('updated_at') or task['created_at']
            
            if status in ('pending', 'processing'):
                return {
                    **base,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "updated_at": updated_at,
                }
            
            if status in ('failed', 'cancelled'):
                error_msg = task['error'] or message
                return {
                    **base,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "updated_at": updated_at,
                    "completed_at": updated_at,
                    "error": error_msg,
                }
            
            if status == 'completed':
                return {
                    **base,
                    "status": "completed",
                    "progress": progress,
                    "message": message,
                    "updated_at": updated_at,
                    "completed_at": updated_at,
                }
            
            return {
                **base,
                "status": status,
                "error": f"Unknown task status: {status}",
            }

        except Exception as e:
            logger.error(f"Get task error: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }
    
    @mcp.tool()
    async def get_task_result(
        task_id: str,
        format: str = "markdown",
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get the primary markdown result or a specific logical result format."""
        if ctx:
            await ctx.info(f"Getting result for task: {task_id}")

        try:
            task = db.get_task(task_id)

            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return {
                    "task_id": task_id,
                    "status": "not_found",
                    "error": f"Task '{task_id}' not found",
                }

            status = task['status']
            updated_at = task.get('updated_at') or task['created_at']
            message = task.get('message', f"Task is {status}")

            if status != 'completed':
                error_msg = task.get('error') or f"Task status is '{status}', not 'completed'"
                return {
                    "task_id": task_id,
                    "status": status,
                    "message": message,
                    "updated_at": updated_at,
                    "error": error_msg,
                }

            result_format, payload, filename = file_manager.read_task_result_format(
                Path(task['task_dir']),
                task['input_filename'],
                task['backend'],
                format,
            )

            return {
                "task_id": task_id,
                "status": "completed",
                "format": result_format,
                "filename": filename,
                "result": payload,
                "completed_at": updated_at,
            }

        except ValueError as e:
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }
        except FileNotFoundError as e:
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Get task result error: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }

    @mcp.tool()
    async def list_task_results(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """List logical result artifacts available for a completed task."""
        if ctx:
            await ctx.info(f"Listing artifacts for task: {task_id}")

        try:
            task = db.get_task(task_id)

            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return {
                    "task_id": task_id,
                    "status": "not_found",
                    "error": f"Task '{task_id}' not found",
                    "artifacts": [],
                }

            status = task['status']
            if status != 'completed':
                return {
                    "task_id": task_id,
                    "status": status,
                    "artifacts": [],
                    "message": "Task not completed. Cannot list result artifacts.",
                }

            artifacts = file_manager.list_task_artifacts(
                Path(task['task_dir']),
                task['input_filename'],
                task['backend'],
            )
            return {
                "task_id": task_id,
                "status": "completed",
                "artifacts": artifacts,
            }
        except Exception as e:
            logger.error(f"List task results error: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
                "artifacts": [],
            }

    @mcp.tool()
    async def get_task_images(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get extracted images from a completed task.
        
        Images are returned as Base64-encoded data URLs.
        
        Args:
            task_id: The task ID returned by create_task_from_file or create_task_from_upload.
            
        Returns:
            Images data:
                - task_id: The task identifier
                - status: Task status
                - images: Dict mapping image filename to Base64 data URL
                - count: Number of images
        """
        if ctx:
            await ctx.info(f"Getting images for task: {task_id}")
        
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return {
                    "task_id": task_id,
                    "status": "not_found",
                    "error": f"Task '{task_id}' not found",
                    "images": {},
                    "count": 0,
                }
            
            status = task['status']
            
            if status != 'completed':
                return {
                    "task_id": task_id,
                    "status": status,
                    "message": "Task not completed. Cannot retrieve images.",
                    "images": {},
                    "count": 0,
                }
            
            output_files = file_manager.get_output_files(
                Path(task['task_dir']),
                task['input_filename'],
                task['backend']
            )
            
            images_dir = output_files['images_dir']
            all_images = file_manager.get_images_as_base64(images_dir)
            
            return {
                "task_id": task_id,
                "status": "completed",
                "images": all_images,
                "count": len(all_images),
            }
            
        except Exception as e:
            logger.error(f"Image extraction error: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
                "images": {},
                "count": 0,
            }
    
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
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            status = task['status']
            
            if status in ('completed', 'failed', 'cancelled'):
                return False
            
            from mineru_mcp.app import _task_scheduler
            
            if _task_scheduler and status == 'processing':
                _task_scheduler.processor.cancel_task(task_id)
            
            state = TaskStateService(db)
            cancelled = state.cancel(task_id, "Task cancelled by user")
            logger.info(f"Task {task_id} cancelled")
            return cancelled
            
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
        
        Args:
            status: Filter by status (optional).
            limit: Maximum number of tasks to return (default 10).
            
        Returns:
            List of task dictionaries with task_id, filename, status, progress, timestamps.
        """
        if ctx:
            await ctx.debug(f"Listing tasks: status={status}, limit={limit}")
        
        try:
            if status:
                tasks = db.fetch_all(
                    "SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                )
            else:
                tasks = db.fetch_all(
                    "SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            
            return [
                {
                    "task_id": t["task_id"],
                    "filename": t["filename"],
                    "status": t["status"],
                    "progress": t.get("progress", 0),
                    "message": t.get("message", ""),
                    "created_at": t["created_at"],
                    "updated_at": t.get("updated_at") or t["created_at"],
                }
                for t in tasks
            ]
            
        except Exception as e:
            logger.error(f"List tasks error: {e}")
            return []
    
    @mcp.tool()
    async def list_parsing_backends() -> list[dict[str, Any]]:
        """List all supported parsing backends.
        
        Returns:
            List of backend dictionaries with name and description.
        """
        backend_list = [
            {"name": "pipeline", "description": "Traditional pipeline (no VLM, multi-language support)"},
            {"name": "vlm-auto-engine", "description": "Local VLM engine (Chinese/English only)"},
            {"name": "vlm-http-client", "description": "Remote VLM via OpenAI-compatible API (Chinese/English only)"},
            {"name": "hybrid-auto-engine", "description": "Local OCR + local VLM (multi-language support)"},
            {"name": "hybrid-http-client", "description": "Local OCR + remote VLM (multi-language, recommended)"},
        ]
        
        return backend_list
    
    @mcp.tool()
    async def list_supported_file_formats() -> list[dict[str, Any]]:
        """List all supported file formats.
        
        Returns:
            List of format dictionaries with extension and mimetype.
        """
        formats = [
            {"extension": ".pdf", "mimetype": "application/pdf"},
            {"extension": ".png", "mimetype": "image/png"},
            {"extension": ".jpg", "mimetype": "image/jpeg"},
            {"extension": ".jpeg", "mimetype": "image/jpeg"},
        ]
        
        return formats
    
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
