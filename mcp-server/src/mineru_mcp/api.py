"""
REST API Layer

FastAPI routes for MinerU PDF parsing.
Mounted under /api in the unified Starlette app.

Response structure aligned with markitdown-server for consistency.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from loguru import logger

from mineru_mcp.config import get_config
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
    TaskImagesResponse,
    CancelTaskResponse,
    BackendsResponse,
    BackendInfo,
    QueueStatsResponse,
    QueueStatsWrapper,
    ErrorResponse,
)
from mineru_mcp.validation import (
    validate_upload_file,
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception
from mineru_mcp.task_queue import TaskDatabase, FileManager, TaskStateService


__version__ = "0.2.0"


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
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    config = get_config()
    db = TaskDatabase(db_path=config.db_path)
    file_manager = FileManager(output_root=config.output_root)
    
    @app.get("/", response_model=HealthResponse)
    async def root():
        """Root endpoint."""
        return _build_health_response()
    
    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check endpoint (no authentication required)."""
        return _build_health_response()
    
    def _build_health_response() -> HealthResponse:
        """Build health response with scheduler/auth/queue status."""
        from mineru_mcp.app import _task_scheduler
        from mineru_mcp.auth import is_auth_required
        
        scheduler_running = bool(_task_scheduler and _task_scheduler._running)
        
        queue_stats = None
        if _task_scheduler:
            stats = _task_scheduler.get_stats()
            queue_stats = QueueStatsResponse(
                pending=stats.get("pending", 0),
                processing=stats.get("processing", 0),
                completed=stats.get("completed", 0),
                failed=stats.get("failed", 0),
                cancelled=stats.get("cancelled", 0),
            )
        
        status = "healthy" if scheduler_running else "degraded"
        
        return HealthResponse(
            status=status,
            version=__version__,
            uptime=time.time() - _get_start_time(),
            scheduler_running=scheduler_running,
            auth_required=is_auth_required(),
            queue_stats=queue_stats,
        )

    def _get_completed_task_and_output(task_id: str) -> tuple[dict, dict]:
        task = db.get_task(task_id)

        if task is None:
            logger.warning(f"Task not found: {task_id}")
            raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())

        status = TaskStatus(task["status"])
        if status != TaskStatus.COMPLETED:
            raise HTTPException(400, ErrorResponse(status="error", error="TASK_NOT_COMPLETED", message=f"Task status is '{status.value}', not 'completed'").model_dump())

        output_files = file_manager.get_output_files(
            Path(task["task_dir"]),
            task["input_filename"],
            task["backend"],
        )
        return task, output_files

    def _stage_upload_record(safe_filename: str, content: bytes, mime_type: str) -> tuple[dict, datetime]:
        upload = file_manager.save_uploaded_content(safe_filename, content, mime_type)
        db.create_upload(
            upload_id=upload["upload_id"],
            file_name=upload["file_name"],
            mime_type=upload["mime_type"],
            size_bytes=upload["size_bytes"],
            sha256=upload["sha256"],
            file_path=str(upload["file_path"]),
        )

        upload_record = db.get_upload(upload["upload_id"])
        created_at = datetime.fromisoformat(upload_record["created_at"]) if upload_record else datetime.now()
        return upload, created_at

    def _submit_task_from_upload_request(request: SubmitUploadedTaskRequest) -> SubmitTaskResponse:
        upload = db.get_upload(request.upload_id)
        if upload is None:
            raise HTTPException(404, ErrorResponse(status="error", error="UPLOAD_NOT_FOUND", message="Upload not found").model_dump())

        if upload["status"] != UploadStatus.UPLOADED.value:
            raise HTTPException(400, ErrorResponse(status="error", error="UPLOAD_NOT_AVAILABLE", message=f"Upload status is '{upload['status']}', expected 'uploaded'").model_dump())

        effective_backend = request.backend if request.backend is not None else config.default_backend
        effective_server_url = request.server_url if request.server_url is not None else config.get_vlm_server_url()
        validated_backend = validate_backend(effective_backend)
        validated_lang = validate_language(request.lang)
        validate_page_range(request.start_page_id, request.end_page_id)

        source_path = Path(upload["file_path"])
        if not source_path.exists():
            raise HTTPException(404, ErrorResponse(status="error", error="UPLOAD_FILE_MISSING", message="Uploaded file is missing").model_dump())

        consumed = db.consume_upload(request.upload_id)
        if not consumed:
            raise HTTPException(409, ErrorResponse(status="error", error="UPLOAD_ALREADY_CONSUMED", message="Upload has already been consumed").model_dump())

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
                formula_enable=request.formula_enable,
                table_enable=request.table_enable,
                image_analysis=request.image_analysis,
                start_page_id=request.start_page_id,
                end_page_id=request.end_page_id,
                server_url=effective_server_url,
                timeout_seconds=config.task_timeout,
            )
        except Exception:
            db.release_upload(request.upload_id)
            raise

        task = db.get_task(task_id)
        created_at = datetime.fromisoformat(task["created_at"]) if task else datetime.now()

        return SubmitTaskResponse(
            task_id=task_id,
            message="Task submitted successfully",
            created_at=created_at,
        )
    
    @app.get("/stats", response_model=QueueStatsWrapper)
    async def get_queue_stats():
        """Get task queue statistics."""
        stats = QueueStatsResponse(
            pending=db.count("SELECT COUNT(*) FROM tasks WHERE status = 'pending'"),
            processing=db.count("SELECT COUNT(*) FROM tasks WHERE status = 'processing'"),
            completed=db.count("SELECT COUNT(*) FROM tasks WHERE status = 'completed'"),
            failed=db.count("SELECT COUNT(*) FROM tasks WHERE status = 'failed'"),
            cancelled=db.count("SELECT COUNT(*) FROM tasks WHERE status = 'cancelled'"),
        )
        
        return QueueStatsWrapper(queue_stats=stats, total=stats.pending + stats.processing + stats.completed + stats.failed + stats.cancelled)
    
    @app.get("/backends", response_model=BackendsResponse)
    async def list_backends():
        """List all supported parsing backends."""
        backend_list = [
            BackendInfo(name="pipeline", description="Traditional pipeline (no VLM, multi-language support)"),
            BackendInfo(name="vlm-auto-engine", description="Local VLM engine (Chinese/English only)"),
            BackendInfo(name="vlm-http-client", description="Remote VLM via OpenAI-compatible API (Chinese/English only)"),
            BackendInfo(name="hybrid-auto-engine", description="Local OCR + local VLM (multi-language support)"),
            BackendInfo(name="hybrid-http-client", description="Local OCR + remote VLM (multi-language, recommended)"),
        ]
        
        return BackendsResponse(backends=backend_list)
    
    @app.post("/tasks", response_model=SubmitTaskResponse)
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
            SubmitTaskResponse with task_id, message, and created_at.
        """
        try:
            effective_backend = backend if backend is not None else config.default_backend
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            
            logger.info(f"Received file upload for async task: {safe_filename}")
            
            task_id, task_dir = file_manager.create_task_dir()
            
            input_filename = safe_filename
            input_path = task_dir / input_filename
            input_path.write_bytes(content)
            
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
            
            task = db.get_task(task_id)
            created_at = datetime.fromisoformat(task['created_at']) if task else datetime.now()
            
            logger.info(f"Task {task_id} submitted to queue")
            
            return SubmitTaskResponse(
                task_id=task_id,
                message="Task submitted successfully",
                created_at=created_at,
            )
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            raise HTTPException(400, ErrorResponse(status="error", error=e.code, message=e.message).model_dump())
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/uploads", response_model=UploadResponse)
    async def create_upload(file: UploadFile = File(..., description="PDF/image file to stage for later task submission")):
        """Stage a file upload and return an upload_id for later task creation."""
        try:
            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            mime_type = file.content_type or "application/octet-stream"

            upload, created_at = _stage_upload_record(safe_filename, content, mime_type)

            return UploadResponse(
                upload_id=upload["upload_id"],
                status=UploadStatus.UPLOADED,
                file_name=upload["file_name"],
                mime_type=upload["mime_type"],
                size_bytes=upload["size_bytes"],
                sha256=upload["sha256"],
                created_at=created_at,
            )

        except ValidationError as e:
            logger.warning(f"Upload validation error: {e.code} - {e.message}")
            raise HTTPException(400, ErrorResponse(status="error", error=e.code, message=e.message).model_dump())
        except Exception as e:
            logger.error(f"Create upload error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/uploads/submit", response_model=SubmitTaskResponse)
    async def upload_and_submit_task(
        file: UploadFile = File(..., description="PDF/image file to stage and submit immediately"),
        backend: str = Form(default=None),
        lang: str = Form(default="ch"),
        formula_enable: bool = Form(default=True),
        table_enable: bool = Form(default=True),
        image_analysis: bool = Form(default=True),
        server_url: str = Form(default=None),
        start_page_id: int = Form(default=0),
        end_page_id: int = Form(default=99999),
    ):
        """Upload a file and immediately create a parsing task.

        This hides the intermediate upload_id from callers while reusing the
        staged-upload flow internally.
        """
        try:
            effective_backend = backend if backend is not None else config.default_backend
            validate_backend(effective_backend)
            validate_language(lang)
            validate_page_range(start_page_id, end_page_id)

            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            mime_type = file.content_type or "application/octet-stream"
            upload, _ = _stage_upload_record(safe_filename, content, mime_type)

            submit_request = SubmitUploadedTaskRequest(
                upload_id=upload["upload_id"],
                backend=backend,
                lang=lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                server_url=server_url,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
            )
            return _submit_task_from_upload_request(submit_request)

        except HTTPException:
            raise
        except ValidationError as e:
            logger.warning(f"Upload-and-submit validation error: {e.code} - {e.message}")
            raise HTTPException(400, ErrorResponse(status="error", error=e.code, message=e.message).model_dump())
        except Exception as e:
            logger.error(f"Upload-and-submit error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/tasks/from-upload", response_model=SubmitTaskResponse)
    async def submit_uploaded_task(request: SubmitUploadedTaskRequest):
        """Create a parsing task from a previously uploaded file."""
        try:
            return _submit_task_from_upload_request(request)

        except HTTPException:
            raise
        except ValidationError as e:
            logger.warning(f"Submit uploaded task validation error: {e.code} - {e.message}")
            raise HTTPException(400, ErrorResponse(status="error", error=e.code, message=e.message).model_dump())
        except Exception as e:
            logger.error(f"Submit uploaded task error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.get("/tasks/{task_id}", response_model=TaskDetailResponse)
    async def get_task_status(task_id: str, return_md: bool = True):
        """Get the status and result of a parsing task.

        Checks task progress and returns status information.
        Call repeatedly until status is "completed" or "failed".

        Args:
            task_id: The task ID returned by POST /tasks.
            return_md: Include markdown content when task is completed.

        Returns:
            TaskDetailResponse with status metadata and optional result/error.
        """
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            
            status = TaskStatus(task['status'])
            progress = task.get('progress', 0)
            message = task.get('message', f"Task is {status.value}")
            created_at = datetime.fromisoformat(task['created_at'])
            updated_at = datetime.fromisoformat(task.get('updated_at') or task['created_at'])
            started_at = datetime.fromisoformat(task['started_at']) if task.get('started_at') else None
            completed_at = datetime.fromisoformat(task['completed_at']) if task.get('completed_at') else None
            markdown = None
            error = task.get('error')

            if status == TaskStatus.COMPLETED and return_md:
                output_files = file_manager.get_output_files(
                    Path(task['task_dir']),
                    task['input_filename'],
                    task['backend']
                )
                markdown = file_manager.get_markdown_content(output_files['md'])
            
            return TaskDetailResponse(
                task_id=task_id,
                status=status,
                progress=progress,
                message=message,
                created_at=created_at,
                updated_at=updated_at,
                started_at=started_at,
                completed_at=completed_at,
                markdown=markdown,
                error=error,
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get task error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    @app.get("/tasks/{task_id}/result", response_model=TaskResultResponse)
    async def get_task_result(task_id: str):
        """Get the markdown result of a completed task.

        Args:
            task_id: The task ID returned by POST /tasks.

        Returns:
            TaskResultResponse with markdown content.
        """
        try:
            task, output_files = _get_completed_task_and_output(task_id)
            status = TaskStatus(task['status'])
            
            md_path = output_files['md']
            markdown_content = file_manager.get_markdown_content(md_path)
            
            return TaskResultResponse(
                task_id=task_id,
                status=status,
                markdown=markdown_content,
                error=None,
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get task result error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    @app.get("/tasks/{task_id}/images", response_model=TaskImagesResponse)
    async def get_task_images(task_id: str, request: Request):
        """Get extracted images from a completed task.
        
        Images are returned as Base64-encoded data URLs and structured metadata.
        
        Args:
            task_id: The task ID returned by POST /tasks.
            
        Returns:
            TaskImagesResponse with images dict and count.
        """
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            
            status = TaskStatus(task['status'])
            
            if status != TaskStatus.COMPLETED:
                return TaskImagesResponse(
                    task_id=task_id,
                    status=status,
                    images={},
                    count=0,
                )
            
            output_files = file_manager.get_output_files(
                Path(task['task_dir']),
                task['input_filename'],
                task['backend']
            )
            
            images_dir = output_files['images_dir']
            markdown_content = file_manager.get_markdown_content(output_files['md'])
            all_images = file_manager.get_images_as_base64(images_dir)
            image_items = file_manager.list_images(images_dir, markdown_content)

            for item in image_items:
                item['url'] = str(request.url_for("get_task_image_file", task_id=task_id, image_name=item['filename']))
            
            return TaskImagesResponse(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                images=all_images,
                items=image_items,
                count=len(all_images),
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Image extraction error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.get("/tasks/{task_id}/images/{image_name:path}", name="get_task_image_file")
    async def get_task_image_file(task_id: str, image_name: str):
        """Serve an extracted image file for a completed task."""
        try:
            _, output_files = _get_completed_task_and_output(task_id)
            images_dir = output_files["images_dir"]

            try:
                image_path = file_manager.resolve_task_image_path(images_dir, image_name)
            except ValueError:
                raise HTTPException(400, ErrorResponse(status="error", error="INVALID_IMAGE_PATH", message="Invalid image path").model_dump())

            if not image_path.exists() or not image_path.is_file():
                raise HTTPException(404, ErrorResponse(status="error", error="IMAGE_NOT_FOUND", message="Image not found").model_dump())

            return FileResponse(image_path, media_type=file_manager.get_image_mime_type(image_path), filename=image_path.name)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Serve task image error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    @app.delete("/tasks/{task_id}", response_model=CancelTaskResponse)
    async def cancel_task(task_id: str):
        """Cancel a pending or processing task.
        
        Args:
            task_id: The task ID to cancel.
            
        Returns:
            CancelTaskResponse with cancellation status.
        """
        try:
            task = db.get_task(task_id)
            
            if task is None:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            
            status = TaskStatus(task['status'])
            
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return CancelTaskResponse(
                    task_id=task_id,
                    cancelled=False,
                    message=f"Task already in status '{status.value}'",
                )
            
            from mineru_mcp.app import _task_scheduler
            
            if _task_scheduler and status == TaskStatus.PROCESSING:
                _task_scheduler.processor.cancel_task(task_id)
            
            state = TaskStateService(db)
            cancelled = state.cancel(task_id, "Task cancelled by user")
            
            return CancelTaskResponse(
                task_id=task_id,
                cancelled=cancelled,
                message="Task cancelled successfully" if cancelled else "Task could not be cancelled",
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Cancel task error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
    return app
