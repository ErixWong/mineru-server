"""
MCP Server Implementation

FastMCP server that exposes MinerU PDF parsing capabilities via local task queue.
Directly calls MinerU core functions instead of HTTP API.
"""

import base64
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from mineru_mcp.config import get_config, MCPConfig
from mineru_mcp.validation import (
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception, task_not_found
from mineru_mcp.task_queue import TaskDatabase, FileManager


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
    async def submit_task(
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
        """Submit a PDF parsing task from base64 content (asynchronous mode).
        
        This tool submits a task and returns immediately with a task ID.
        Use get_task to check progress and retrieve results when ready.
        
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
            Task submission result:
                - task_id: Unique task identifier for tracking
                - status: "pending"
                - message: Guidance for next steps
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
            
            if ctx:
                await ctx.info(f"Task submitted: {task_id}")
            
            logger.info(f"Task {task_id} submitted to queue")
            
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Task submitted successfully. Use get_task to check progress.",
            }
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            return from_exception(e).to_dict()
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def get_task(
        task_id: str,
        return_md: bool = True,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get the status and result of a parsing task.

        Checks task progress and returns results when completed.
        Call repeatedly until status is "completed" or "failed".

        Args:
            task_id: The task ID returned by submit_task.
            return_md: Include markdown content when task is completed.

        Returns:
            Task information:
                - pending/processing: status and message
                - completed: status and markdown (if return_md=true)
                - failed: status and error
        """
        if ctx:
            await ctx.debug(f"Checking task: {task_id}")

        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return task_not_found(task_id).to_dict()
            
            status = task['status']
            
            if status in ('pending', 'processing'):
                return {
                    "task_id": task_id,
                    "status": status,
                    "message": f"Task is {status}",
                }
            
            if status == 'failed':
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": task['error'] or "Unknown error",
                }
            
            if status == 'completed':
                if not return_md:
                    return {
                        "task_id": task_id,
                        "status": "completed",
                        "message": "Task completed. Use get_task with return_md=true or get_images to retrieve content.",
                    }
                
                output_files = file_manager.get_output_files(
                    Path(task['task_dir']),
                    task['input_filename'],
                    task['backend']
                )
                
                md_path = output_files['md']
                markdown_content = file_manager.get_markdown_content(md_path)
                
                return {
                    "task_id": task_id,
                    "status": "completed",
                    "markdown": markdown_content,
                }
            
            return {
                "task_id": task_id,
                "status": status,
                "message": f"Unknown task status: {status}",
            }

        except Exception as e:
            logger.error(f"Get task error: {e}")
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def get_images(
        task_id: str,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get extracted images from a completed task.
        
        Images are returned as Base64-encoded data URLs.
        
        Args:
            task_id: The task ID returned by submit_task.
            
        Returns:
            Images data:
                - task_id: The task identifier
                - status: Task status
                - images: Dict mapping image filename to Base64 data URL
        """
        if ctx:
            await ctx.info(f"Getting images for task: {task_id}")
        
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                return task_not_found(task_id).to_dict()
            
            if task['status'] != 'completed':
                return {
                    "task_id": task_id,
                    "status": task['status'],
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
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def list_backends() -> dict[str, Any]:
        """List all supported parsing backends.
        
        Returns:
            List of backend names with descriptions.
        """
        backend_descriptions = {
            "pipeline": "Traditional pipeline (no VLM, multi-language support)",
            "vlm-auto-engine": "Local VLM engine (Chinese/English only)",
            "vlm-http-client": "Remote VLM via OpenAI-compatible API (Chinese/English only)",
            "hybrid-auto-engine": "Local OCR + local VLM (multi-language support)",
            "hybrid-http-client": "Local OCR + remote VLM (multi-language, recommended)",
        }
        
        return {
            "backends": list(backend_descriptions.keys()),
            "descriptions": backend_descriptions,
        }
    
    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """Check task queue health status.
        
        Returns:
            Health status:
                - healthy: True if task queue is running
                - scheduler_running: Scheduler status
                - queue_stats: Task counts by status
                - auth_required: Whether authentication is enabled
        """
        try:
            from mineru_mcp.app import _task_scheduler
            from mineru_mcp.auth import is_auth_required
            
            auth_required = is_auth_required()
            
            if _task_scheduler:
                stats = _task_scheduler.get_stats()
                
                return {
                    "healthy": stats['running'],
                    "scheduler_running": stats['running'],
                    "queue_stats": stats,
                    "auth_required": auth_required,
                    "message": "Task queue is running",
                }
            else:
                return {
                    "healthy": False,
                    "scheduler_running": False,
                    "queue_stats": {},
                    "auth_required": auth_required,
                    "message": "Task scheduler not initialized",
                }
                
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return from_exception(e).to_dict()
    
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