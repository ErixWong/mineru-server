"""
MCP Server Implementation

FastMCP server that exposes MinerU PDF parsing capabilities.
"""

import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from mineru_mcp.config import get_config, MCPConfig
from mineru_mcp.mineru_client import get_client, MinerUClient
from mineru_mcp.validation import (
    validate_file_path,
    validate_task_id,
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import (
    from_exception,
    task_not_found,
    task_still_processing,
    mineru_api_unavailable,
)
from mineru_mcp.utils import aggregate_markdown, save_base64_file, cleanup_temp_file


# Configure logging
def setup_logging(log_level: str = "INFO") -> None:
    """Setup loguru logging."""
    logger.remove()
    logger.add(sys.stderr, level=log_level.upper())


# Create FastMCP server
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
    
    # Log configuration
    logger.info(f"Creating MCP Server: {config.server_name}")
    logger.info(f"Mode: {config.server_mode}")
    logger.info(f"MinerU API: {config.mineru_api_base}")
    if config.http_auth_token:
        logger.info("Authentication: Enabled")
    
    # Create FastMCP server
    # Use stateless_http and json_response for production HTTP mode
    mcp = FastMCP(
        config.server_name,
        stateless_http=True if config.is_http_mode() else False,
        json_response=True if config.is_http_mode() else False,
    )
    
    # Get MinerU client
    client = get_client()
    
    # Register tools
    @mcp.tool()
    async def parse_pdf(
        file_base64: str,
        file_name: Optional[str] = None,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Parse a PDF document from base64 content and extract markdown.
        
        This tool accepts base64-encoded PDF content, saves it to a temporary file,
        parses it using MinerU, and returns the extracted markdown content.
        
        Args:
            file_base64: Base64-encoded PDF file content (required).
            file_name: Optional file name for display and extension detection.
            backend: Parsing backend:
                - pipeline: Traditional pipeline (no VLM, multi-language)
                - vlm-auto-engine: Local VLM engine (Chinese/English only)
                - vlm-http-client: Remote VLM via OpenAI-compatible API
                - hybrid-auto-engine: Local OCR + local VLM (multi-language)
                - hybrid-http-client: Local OCR + remote VLM (multi-language, recommended)
            lang: Document language for OCR (ch, en, korean, japan, etc.).
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).
            
        Returns:
            Parsing result containing:
                - task_id: Unique task identifier
                - status: Task status (completed/failed)
                - results: Dict with markdown content and images
        """
        if ctx:
            await ctx.info(f"Received base64 file: {file_name or 'unnamed'}")
        
        temp_file_path = None
        
        try:
            effective_backend = backend if backend is not None else config.default_backend
            effective_server_url = server_url if server_url is not None else config.get_vlm_server_url()
            
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            logger.info(f"Saving base64 file: {file_name or 'unnamed'}")
            
            temp_file_path = save_base64_file(file_base64, file_name)
            logger.info(f"Saved to temporary file: {temp_file_path.name}")
            
            logger.debug(f"Backend: {validated_backend}, Lang: {validated_lang}")
            if effective_server_url:
                logger.debug(f"VLM Server URL: {effective_server_url}")
            
            result = await client.parse_pdf_sync(
                file_path=str(temp_file_path),
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                server_url=effective_server_url,
                return_md=True,
                return_images=False,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
            )
            
            if ctx:
                await ctx.info("PDF parsing completed successfully")
            
            cleanup_temp_file(temp_file_path)
            
            return result
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            return from_exception(e).to_dict()
        except Exception as e:
            logger.error(f"Parse error: {e}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def submit_task(
        file_base64: str,
        file_name: Optional[str] = None,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Submit a PDF parsing task from base64 content.
        
        This tool accepts base64-encoded PDF content, submits it for asynchronous
        parsing, and returns a task ID for tracking progress.
        
        Args:
            file_base64: Base64-encoded PDF file content (required).
            file_name: Optional file name for display and extension detection.
            backend: Parsing backend:
                - pipeline: Traditional pipeline (no VLM, multi-language)
                - vlm-auto-engine: Local VLM engine (Chinese/English only)
                - vlm-http-client: Remote VLM via OpenAI-compatible API
                - hybrid-auto-engine: Local OCR + local VLM (multi-language)
                - hybrid-http-client: Local OCR + remote VLM (multi-language, recommended)
            lang: Document language for OCR (ch, en, korean, japan, etc.).
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).
            
        Returns:
            Task submission result containing:
                - task_id: Unique task identifier for tracking
                - status: "pending"
                - message: Guidance for next steps
        """
        if ctx:
            await ctx.info(f"Submitting task for: {file_name or 'unnamed'}")
        
        temp_file_path = None
        
        try:
            effective_backend = backend if backend is not None else config.default_backend
            effective_server_url = server_url if server_url is not None else config.get_vlm_server_url()
            
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            logger.info(f"Saving base64 file: {file_name or 'unnamed'}")
            
            temp_file_path = save_base64_file(file_base64, file_name)
            logger.info(f"Saved to temporary file: {temp_file_path.name}")
            
            logger.debug(f"Backend: {validated_backend}, Lang: {validated_lang}")
            if effective_server_url:
                logger.debug(f"VLM Server URL: {effective_server_url}")
            
            task_id = await client.submit_task(
                file_path=str(temp_file_path),
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                server_url=effective_server_url,
                return_md=True,
                return_images=True,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
            )
            
            cleanup_temp_file(temp_file_path)
            
            if ctx:
                await ctx.info(f"Task submitted: {task_id}")
            
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Task submitted successfully. Use get_task to check progress.",
            }
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            return from_exception(e).to_dict()
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def get_task(
        task_id: str,
        return_md: bool = True,
        ctx: Context[ServerSession, None] = None,
    ) -> dict[str, Any]:
        """Get the status and result of a parsing task.

        This unified tool checks task progress and returns results when
        completed. Call repeatedly until status is "completed" or "failed".

        Args:
            task_id: The task ID returned by submit_task.
            return_md: Include aggregated markdown content when task is
                completed. Set to false for a lightweight status-only check.

        Returns:
            Task information:

            When pending/processing:
                - task_id: The task identifier
                - status: "pending" or "processing"
                - message: Progress description

            When completed (return_md=true):
                - task_id: The task identifier
                - status: "completed"
                - markdown: Aggregated markdown content from all pages

            When completed (return_md=false):
                - task_id: The task identifier
                - status: "completed"
                - message: "Task completed. Use get_task with return_md=true
                  or get_images to retrieve content."

            When failed:
                - task_id: The task identifier
                - status: "failed"
                - error: Error description
        """
        if ctx:
            await ctx.debug(f"Checking task: {task_id}")

        try:
            validated_task_id = validate_task_id(task_id)

            status_info = await client.get_task_status(validated_task_id)
            task_status = status_info.get("status", "unknown")

            if task_status in ("pending", "processing"):
                return {
                    "task_id": validated_task_id,
                    "status": task_status,
                    "message": status_info.get("message", f"Task is {task_status}"),
                }

            if task_status == "failed":
                return {
                    "task_id": validated_task_id,
                    "status": "failed",
                    "error": status_info.get("error", "Unknown error"),
                }

            if task_status == "completed":
                if not return_md:
                    return {
                        "task_id": validated_task_id,
                        "status": "completed",
                        "message": "Task completed. Use get_task with return_md=true or get_images to retrieve content.",
                    }

                result = await client.get_task_result(
                    task_id=validated_task_id,
                    return_md=True,
                    return_images=False,
                )

                return {
                    "task_id": validated_task_id,
                    "status": "completed",
                    "markdown": aggregate_markdown(result),
                }

            return {
                "task_id": validated_task_id,
                "status": task_status,
                "message": f"Unknown task status: {task_status}",
            }

        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            return from_exception(e).to_dict()
        except ValueError:
            logger.warning(f"Task not found: {task_id}")
            return task_not_found(task_id).to_dict()
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
            # Validate task ID
            validated_task_id = validate_task_id(task_id)
            
            result = await client.get_task_result(
                task_id=validated_task_id,
                return_md=False,
                return_images=True,
            )
            
            # Check if task is still processing
            if result.get("status") == "processing":
                return task_still_processing(validated_task_id).to_dict()
            
            # Extract images from results
            all_images: dict[str, str] = {}
            if "results" in result:
                for file_name, file_result in result["results"].items():
                    if "images" in file_result:
                        all_images.update(file_result["images"])
            
            return {
                "task_id": validated_task_id,
                "status": result.get("status", "unknown"),
                "images": all_images,
                "count": len(all_images),
            }
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            return from_exception(e).to_dict()
        except ValueError:
            logger.warning(f"Task not found: {task_id}")
            return task_not_found(task_id).to_dict()
        except Exception as e:
            logger.error(f"Image extraction error: {e}")
            return from_exception(e).to_dict()
    
    @mcp.tool()
    async def list_backends() -> dict[str, Any]:
        """List all supported parsing backends.
        
        Returns:
            List of backend names with descriptions:
                - pipeline: Traditional pipeline (no VLM, multi-language)
                - vlm-auto-engine: Local VLM (Chinese/English only)
                - vlm-http-client: Remote VLM via API (Chinese/English only)
                - hybrid-auto-engine: Local OCR + local VLM (multi-language)
                - hybrid-http-client: Local OCR + remote VLM (multi-language, recommended)
        """
        backends = await client.list_backends()
        
        # Add descriptions
        backend_descriptions = {
            "pipeline": "Traditional pipeline (no VLM, multi-language support)",
            "vlm-auto-engine": "Local VLM engine (Chinese/English only)",
            "vlm-http-client": "Remote VLM via OpenAI-compatible API (Chinese/English only)",
            "hybrid-auto-engine": "Local OCR + local VLM (multi-language support)",
            "hybrid-http-client": "Local OCR + remote VLM (multi-language, recommended)",
        }
        
        return {
            "backends": backends,
            "descriptions": {
                b: backend_descriptions.get(b, "Unknown backend")
                for b in backends
            },
        }
    
    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """Check if MinerU API is healthy.
        
        Returns:
            Health status:
                - healthy: True if MinerU is running
                - message: Status message
                - mineru_api_base: The MinerU API base URL
        """
        try:
            is_healthy = await client.health_check()
            
            if is_healthy:
                return {
                    "healthy": True,
                    "message": "MinerU API is running",
                    "mineru_api_base": config.mineru_api_base,
                }
            else:
                return mineru_api_unavailable().to_dict()
                
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return from_exception(e).to_dict()
    
    return mcp


# Global server instance
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
