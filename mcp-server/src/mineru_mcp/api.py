"""
REST API Layer

FastAPI routes for MinerU PDF parsing.
Mounted under /api in the unified Starlette app.
"""

import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.validation import (
    validate_upload_file,
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception, task_not_found
from mineru_mcp.task_queue import TaskDatabase, FileManager


def _get_start_time() -> float:
    """Get the shared start time from app module."""
    from mineru_mcp.app import _start_time
    return _start_time


def create_api_app() -> FastAPI:
    """Create FastAPI app for REST API.
    
    Returns:
        FastAPI application instance.
    """
    app = FastAPI(
        title="MinerU MCP Server API",
        description="REST API for MinerU PDF parsing",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    config = get_config()
    db = TaskDatabase(db_path=config.db_path)
    file_manager = FileManager(output_root=config.output_root)
    
    @app.get("/health")
    async def health():
        """Health check endpoint (no authentication required)."""
        from mineru_mcp.auth import is_auth_required
        from mineru_mcp.app import _task_scheduler
        
        auth_required = is_auth_required()
        
        if _task_scheduler:
            stats = _task_scheduler.get_stats()
            scheduler_running = stats['running']
        else:
            scheduler_running = False
            stats = {}
        
        return {
            "status": "healthy" if scheduler_running else "degraded",
            "uptime": time.time() - _get_start_time(),
            "scheduler_running": scheduler_running,
            "auth_required": auth_required,
            "queue_stats": stats,
        }
    
    @app.get("/stats")
    async def get_queue_stats():
        """Get task queue statistics."""
        stats = {
            "pending": db.count("SELECT COUNT(*) FROM tasks WHERE status = 'pending'"),
            "processing": db.count("SELECT COUNT(*) FROM tasks WHERE status = 'processing'"),
            "completed": db.count("SELECT COUNT(*) FROM tasks WHERE status = 'completed'"),
            "failed": db.count("SELECT COUNT(*) FROM tasks WHERE status = 'failed'"),
            "cancelled": db.count("SELECT COUNT(*) FROM tasks WHERE status = 'cancelled'"),
        }
        
        return {
            "queue_stats": stats,
            "total": sum(stats.values()),
        }
    
    @app.get("/backends")
    async def list_backends():
        """List all supported parsing backends."""
        backend_descriptions = {
            "pipeline": "Traditional pipeline (no VLM, multi-language support)",
            "vlm-auto-engine": "Local VLM engine (Chinese/English only)",
            "vlm-http-client": "Remote VLM via OpenAI-compatible API (Chinese/English only)",
            "hybrid-auto-engine": "Local OCR + local VLM (multi-language support)",
            "hybrid-http-client": "Local OCR + remote VLM (multi-language, recommended)",
        }
        
        return {
            "backends": [
                {"name": b, "description": backend_descriptions.get(b, "")}
                for b in backend_descriptions.keys()
            ],
        }
    
    @app.post("/tasks")
    async def submit_task(
        file: UploadFile = File(..., description="PDF/image file to parse"),
        backend: str = Form(default=None),
        lang: str = Form(default="ch"),
        formula_enable: bool = Form(default=True),
        table_enable: bool = Form(default=True),
        image_analysis: bool = Form(default=True),
        server_url: str = Form(default=None),
        start_page_id: int = Form(default=0),
        end_page_id: int = Form(default=99999),
    ):
        """Submit PDF parsing task asynchronously (multipart/form-data upload).
        
        Upload a PDF file for asynchronous parsing. Returns task ID immediately.
        Use GET /tasks/{task_id} to check progress and retrieve results.
        
        Args:
            file: PDF file to upload and parse.
            backend: Parsing backend (optional, defaults to config.default_backend).
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            image_analysis: Enable VLM image analysis (generates AI descriptions).
            server_url: VLM server URL (for http-client backends).
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            
        Returns:
            Task ID and status (pending).
        """
        try:
            effective_backend = backend if backend is not None else config.default_backend
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            # Read file content
            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            
            logger.info(f"Received file upload for async task: {safe_filename}")
            
            # Create task directory
            task_id, task_dir = file_manager.create_task_dir()
            
            # Save file
            input_filename = safe_filename
            input_path = task_dir / input_filename
            input_path.write_bytes(content)
            
            # Create task in database
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
                server_url=server_url,
                timeout_seconds=config.task_timeout,
            )
            
            logger.info(f"Task {task_id} submitted to queue")
            
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Task submitted successfully. Use GET /tasks/{task_id} to check progress.",
                "created_at": db.get_task(task_id)['created_at'],
            }
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            raise HTTPException(400, e.to_dict())
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    @app.get("/tasks/{task_id}")
    async def get_task_status(task_id: str, return_md: bool = True):
        """Get the status and result of a parsing task.

        Checks task progress and returns results when completed.
        Call repeatedly until status is "completed" or "failed".

        Args:
            task_id: The task ID returned by POST /tasks.
            return_md: Include markdown content when task is completed.

        Returns:
            Task information:
                - pending/processing: status and message
                - completed: status and markdown (if return_md=true)
                - failed: status and error
        """
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(404, task_not_found(task_id).to_dict())
            
            status = task['status']
            
            if status in ('pending', 'processing'):
                return {
                    "task_id": task_id,
                    "status": status,
                    "message": f"Task is {status}",
                    "created_at": task['created_at'],
                    "started_at": task.get('started_at'),
                }
            
            if status == 'failed':
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": task['error'] or "Unknown error",
                    "created_at": task['created_at'],
                    "completed_at": task.get('completed_at'),
                }
            
            if status == 'completed':
                if not return_md:
                    return {
                        "task_id": task_id,
                        "status": "completed",
                        "message": "Task completed. Use GET /tasks/{task_id}?return_md=true or GET /tasks/{task_id}/images to retrieve content.",
                        "created_at": task['created_at'],
                        "completed_at": task.get('completed_at'),
                    }
                
                output_files = file_manager.get_output_files(
                    Path(task['task_dir']),
                    task['input_filename'],
                    task['backend']
                )
                
                md_path = output_files['md']
                logger.debug(f"MD path: {md_path}, exists: {md_path.exists()}")
                markdown_content = file_manager.get_markdown_content(md_path)
                logger.debug(f"MD content length: {len(markdown_content)}")
                
                return {
                    "task_id": task_id,
                    "status": "completed",
                    "markdown": markdown_content,
                    "created_at": task['created_at'],
                    "completed_at": task.get('completed_at'),
                }
            
            return {
                "task_id": task_id,
                "status": status,
                "message": f"Unknown task status: {status}",
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get task error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    @app.get("/tasks/{task_id}/images")
    async def get_task_images(task_id: str):
        """Get extracted images from a completed task.
        
        Images are returned as Base64-encoded data URLs.
        
        Args:
            task_id: The task ID returned by POST /tasks.
            
        Returns:
            Images data:
                - task_id: The task identifier
                - status: Task status
                - images: Dict mapping image filename to Base64 data URL
        """
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(404, task_not_found(task_id).to_dict())
            
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
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Image extraction error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    return app
