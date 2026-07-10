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
from fastapi.responses import JSONResponse, Response
from starlette.responses import FileResponse
from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.services import get_task_service


def add_deprecation_headers(response: Response) -> Response:
    """Add standard deprecation headers to a response.
    
    Args:
        response: The response to add headers to.
        
    Returns:
        The same response with deprecation headers added.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Jan 2028 00:00:00 GMT"
    response.headers["Link"] = '</api/docs>; rel="deprecation-docs"'
    return response


def wrap_with_deprecation_headers(response, status_code: int = 200):
    """Wrap any response (Pydantic model, dict, or Response) with deprecation headers.
    
    For Pydantic models or dicts, converts to JSONResponse with headers.
    For already-constructed Response objects, adds headers directly.
    
    Args:
        response: The response to wrap (Pydantic model, dict, or Response)
        status_code: HTTP status code for the response
        
    Returns:
        Response with deprecation headers added.
    """
    from fastapi.responses import JSONResponse
    
    # If already a Response, just add headers
    if hasattr(response, 'headers') and hasattr(response, 'body'):
        return add_deprecation_headers(response)
    
    # For Pydantic models or dicts, convert to JSONResponse with headers
    if hasattr(response, 'model_dump'):
        # Pydantic model
        content = response.model_dump(mode="json")
    elif isinstance(response, dict):
        content = response
    else:
        content = response
    
    json_response = JSONResponse(content=content, status_code=status_code)
    return add_deprecation_headers(json_response)


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
    TaskArtifactsResponse,
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
from mineru_mcp.principal import CurrentPrincipal, DEFAULT_SINGLE_USER_PRINCIPAL


__version__ = "0.2.0"


def get_principal_from_request(request: Request) -> CurrentPrincipal:
    """Extract the current principal from the request.
    
    The principal is set by AuthMiddleware in app.py.
    
    Args:
        request: The FastAPI/Starlette request.
        
    Returns:
        CurrentPrincipal object.
        
    Raises:
        RuntimeError: If principal is not set in multi-user auth mode.
    """
    # Try to get from request.state (set by AuthMiddleware)
    if hasattr(request, "state") and hasattr(request.state, "principal"):
        return request.state.principal
    
    # Fallback to default only in single-user / legacy / no-auth modes
    from mineru_mcp.auth import get_auth_mode, AuthMode
    auth_mode = get_auth_mode()
    if auth_mode in (AuthMode.SINGLE_USER, AuthMode.LEGACY_SHARED, AuthMode.NONE):
        return DEFAULT_SINGLE_USER_PRINCIPAL
    
    # Multi-user mode requires principal from middleware
    raise RuntimeError(
        f"Principal not set on request state in {auth_mode.value} auth mode. "
        "Ensure AuthMiddleware is applied before accessing request.state.principal."
    )


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
        """Complete health check endpoint with queue statistics.
        
        Returns full health response including queue statistics.
        For simplified liveness check, use root /health instead.
        
        Returns:
            HealthResponse with full queue statistics.
        """
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
    
    @app.get("/admin/tasks")
    async def admin_list_tasks(request: Request, status: str = "", limit: int = 100):
        """Admin endpoint to list all tasks across all users.
        
        This endpoint is only available to admin principals.
        
        Args:
            request: FastAPI request (for extracting principal).
            status: Optional status filter.
            limit: Maximum number of tasks to return (default 100).
            
        Returns:
            List of all tasks in the system.
        """
        # Get current principal
        principal = get_principal_from_request(request)
        
        # Check admin role
        if not principal.is_admin():
            raise HTTPException(403, ErrorResponse(status="error", error="FORBIDDEN", message="Admin access required").model_dump())
        
        try:
            task_service = get_task_service()
            tasks = task_service.get_tasks_for_principal(principal, status=status, limit=limit)
            
            return tasks
        except Exception as e:
            logger.error(f"Admin list tasks error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
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
        request: Request,
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
            request: FastAPI request (for extracting principal).
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
            # Get current principal
            principal = get_principal_from_request(request)
            
            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            
            logger.info(f"Received file upload for async task: {safe_filename}")
            
            # Use shared TaskService for task creation
            import base64
            task_service = get_task_service()
            result = task_service.create_task_from_base64(
                file_base64=base64.b64encode(content).decode('utf-8'),
                file_name=safe_filename,
                backend=backend,
                lang=lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                server_url=server_url,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                principal=principal,
            )
            
            if result.get("status") == "error":
                raise HTTPException(400, ErrorResponse(status="error", error="TASK_CREATE_ERROR", message=result.get("error", "Failed to create task")).model_dump())
            
            task_id = result.get("task_id")
            created_at_str = result.get("created_at")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
            
            logger.info(f"Task {task_id} submitted to queue")
            
            return SubmitTaskResponse(
                task_id=task_id,
                message="Task submitted successfully",
                created_at=created_at,
            )
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e.code} - {e.message}")
            raise HTTPException(400, ErrorResponse(status="error", error=e.code, message=e.message).model_dump())
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/uploads", response_model=UploadResponse)
    async def create_upload(request: Request, file: UploadFile = File(..., description="PDF/image file to stage for later task submission")):
        """Stage a file upload and return an upload_id for later task creation."""
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            mime_type = file.content_type or "application/octet-stream"

            upload = file_manager.save_uploaded_content(safe_filename, content, mime_type)
            db.create_upload(
                upload_id=upload["upload_id"],
                file_name=upload["file_name"],
                mime_type=upload["mime_type"],
                size_bytes=upload["size_bytes"],
                sha256=upload["sha256"],
                file_path=str(upload["file_path"]),
                owner_id=principal.principal_id,
                owner_type=principal.principal_type.value,
            )

            upload_record = db.get_upload(upload["upload_id"])
            created_at = datetime.fromisoformat(upload_record["created_at"]) if upload_record else datetime.now()

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
        request: Request,
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
            # Get current principal
            principal = get_principal_from_request(request)
            
            effective_backend = backend if backend is not None else config.default_backend
            validate_backend(effective_backend)
            validate_language(lang)
            validate_page_range(start_page_id, end_page_id)

            content = await file.read()
            safe_filename = validate_upload_file(file.filename, content)
            mime_type = file.content_type or "application/octet-stream"
            
            upload = file_manager.save_uploaded_content(safe_filename, content, mime_type)
            db.create_upload(
                upload_id=upload["upload_id"],
                file_name=upload["file_name"],
                mime_type=upload["mime_type"],
                size_bytes=upload["size_bytes"],
                sha256=upload["sha256"],
                file_path=str(upload["file_path"]),
                owner_id=principal.principal_id,
                owner_type=principal.principal_type.value,
            )

            # Use shared TaskService for task creation
            task_service = get_task_service()
            result = task_service.create_task_from_upload(
                upload_id=upload["upload_id"],
                backend=backend,
                lang=lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                server_url=server_url,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                principal=principal,
            )

            if result.get("status") == "error":
                raise HTTPException(400, ErrorResponse(status="error", error="TASK_CREATE_ERROR", message=result.get("error", "Failed to create task")).model_dump())

            task_id = result.get("task_id")
            created_at_str = result.get("created_at")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()

            return SubmitTaskResponse(
                task_id=task_id,
                message="Task submitted successfully",
                created_at=created_at,
            )

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
    async def submit_uploaded_task(http_request: Request, request: SubmitUploadedTaskRequest):
        """Create a parsing task from a previously uploaded file."""
        try:
            # Get current principal
            principal = get_principal_from_request(http_request)
            
            # Use shared TaskService for task creation
            task_service = get_task_service()
            result = task_service.create_task_from_upload(
                upload_id=request.upload_id,
                backend=request.backend,
                lang=request.lang,
                formula_enable=request.formula_enable,
                table_enable=request.table_enable,
                image_analysis=request.image_analysis,
                server_url=request.server_url,
                start_page_id=request.start_page_id,
                end_page_id=request.end_page_id,
                principal=principal,
            )

            if result.get("status") == "error":
                error_msg = result.get("error", "Failed to create task")
                # Determine appropriate error code
                if "not found" in error_msg.lower():
                    raise HTTPException(404, ErrorResponse(status="error", error="UPLOAD_NOT_FOUND", message=error_msg).model_dump())
                elif "already been consumed" in error_msg.lower():
                    raise HTTPException(409, ErrorResponse(status="error", error="UPLOAD_ALREADY_CONSUMED", message=error_msg).model_dump())
                else:
                    raise HTTPException(400, ErrorResponse(status="error", error="TASK_CREATE_ERROR", message=error_msg).model_dump())

            task_id = result.get("task_id")
            created_at_str = result.get("created_at")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()

            return SubmitTaskResponse(
                task_id=task_id,
                message="Task submitted successfully",
                created_at=created_at,
            )

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
    async def get_task_status(request: Request, task_id: str, return_md: bool = True):
        """Get the status and result of a parsing task.

        Checks task progress and returns status information.
        Call repeatedly until status is "completed" or "failed".

        Args:
            request: FastAPI request (for extracting principal).
            task_id: The task ID returned by POST /tasks.
            return_md: Include markdown content when task is completed.

        Returns:
            TaskDetailResponse with status metadata and optional result/error.
        """
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            # Use TaskService with authorization check
            task_service = get_task_service()
            result = task_service.get_task_status_authorized(task_id, principal)
            
            if result.get("status") == "not_found":
                logger.warning(f"Task not found or not authorized: {task_id}")
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            
            # Convert to TaskDetailResponse
            task_data = db.get_task(task_id)
            status = TaskStatus(task_data['status'])
            progress = task_data.get('progress', 0)
            message = task_data.get('message', f"Task is {status.value}")
            created_at = datetime.fromisoformat(task_data['created_at'])
            updated_at = datetime.fromisoformat(task_data.get('updated_at') or task_data['created_at'])
            started_at = datetime.fromisoformat(task_data['started_at']) if task_data.get('started_at') else None
            completed_at = datetime.fromisoformat(task_data['completed_at']) if task_data.get('completed_at') else None
            markdown = None
            error = task_data.get('error')

            if status == TaskStatus.COMPLETED and return_md:
                output_files = file_manager.get_output_files(
                    Path(task_data['task_dir']),
                    task_data['input_filename'],
                    task_data['backend']
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

    @app.get("/tasks/{task_id}/deliverables/download")
    async def download_deliverable(request: Request, task_id: str, download_key: str):
        """Download a single artifact as raw content using the unified artifact-first contract.

        Text artifacts are returned as text/plain or application/json.
        Image artifacts are returned as binary with their native media type.

        Args:
            request: FastAPI request (for extracting principal).
            task_id: The task ID returned by POST /tasks.
            download_key: Controlled relative path from the artifact list.
        """
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            # Use shared TaskService with authorization
            task_service = get_task_service()
            result = task_service.download_deliverable_authorized(task_id, download_key, include_content=True, principal=principal)

            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message=result.get("error", "Task not found")).model_dump())

            if result.get("status") != "completed":
                raise HTTPException(400, ErrorResponse(status="error", error=result.get("status"), message=result.get("error", "Task not completed")).model_dump())

            # Build response based on encoding
            if result.get("encoding") == "utf-8":
                return Response(content=result.get("content", ""), media_type="text/markdown; charset=utf-8")
            elif result.get("encoding") == "json":
                return Response(content=result.get("content", ""), media_type="application/json")
            else:
                # Base64 encoded content
                import base64
                content_bytes = base64.b64decode(result.get("content", ""))
                return Response(content=content_bytes, media_type=result.get("media_type", "application/octet-stream"))

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Download task artifact error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.get("/tasks/{task_id}/deliverables", response_model=TaskArtifactsResponse)
    async def list_deliverables(request: Request, task_id: str):
        """List logical artifacts available for a completed task."""
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            # Use shared TaskService with authorization
            task_service = get_task_service()
            result = task_service.list_deliverables_authorized(task_id, principal)

            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message=result.get("error", "Task not found")).model_dump())

            if result.get("status") != "completed":
                return TaskArtifactsResponse(
                    task_id=task_id,
                    status=TaskStatus(result.get("status", "pending")),
                    artifacts=result.get("artifacts", []),
                )

            return TaskArtifactsResponse(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                artifacts=result.get("artifacts", []),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"List task results error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.get("/tasks/{task_id}/deliverables/images/{image_name:path}", name="get_deliverable_image_file")
    async def get_deliverable_image_file(request: Request, task_id: str, image_name: str):
        """Serve an extracted image file for a completed task."""
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            # Check authorization first
            task_service = get_task_service()
            result = task_service.get_task_status_authorized(task_id, principal)
            
            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            
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
    async def cancel_task(request: Request, task_id: str):
        """Cancel a pending or processing task.

        Args:
            request: FastAPI request (for extracting principal).
            task_id: The task ID to cancel.

        Returns:
            CancelTaskResponse with cancellation status.
        """
        try:
            # Get current principal
            principal = get_principal_from_request(request)
            
            # Use TaskService with authorization check
            task_service = get_task_service()
            result = task_service.cancel_task_authorized(task_id, principal)

            if result.get("error") and "not found" in result.get("error", "").lower():
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())

            # If authorized but task is processing, use scheduler to cancel
            if result.get("cancelled") is not False:
                task = db.get_task(task_id)
                if task and task.get('status') == 'processing':
                    from mineru_mcp.app import _task_scheduler
                    if _task_scheduler:
                        _task_scheduler.processor.cancel_task(task_id)

            return CancelTaskResponse(
                task_id=task_id,
                cancelled=result.get("cancelled", False),
                message=result.get("message", ""),
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Cancel task error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    return app
