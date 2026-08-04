"""
REST API Layer

FastAPI routes for MinerU PDF parsing.
Mounted under /api in the unified Starlette app.

Response structure aligned with markitdown-server for consistency.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from starlette.responses import FileResponse
from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.services import get_task_service
from mineru_mcp import __version__


from mineru_mcp.models import (
    TaskStatus,
    HealthResponse,
    SubmitTaskResponse,
    TaskDetailResponse,
    TaskStatusResponse,
    TaskListResponse,
    TaskArtifactsResponse,
    CancelTaskResponse,
    BackendsResponse,
    BackendInfo,
    QueueStatsResponse,
    QueueStatsWrapper,
    ErrorResponse,
)
from mineru_mcp.validation import (
    ValidationError,
)
from mineru_mcp.errors import from_exception
from mineru_mcp.utils import cleanup_temp_file, save_upload_stream
from mineru_mcp.postprocess import build_postprocess_output_path
from mineru_mcp.task_queue import TaskDatabase, FileManager, TaskStateService
from mineru_mcp.principal import CurrentPrincipal
from mineru_mcp.admin_api import admin_router


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
    
    raise RuntimeError(
        "Principal not set on request state. Ensure AuthMiddleware is applied "
        "before accessing request.state.principal."
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

        from mineru_mcp.task_queue.file_manager import resolve_stored_filename
        output_files = file_manager.get_output_files(
            Path(task["task_dir"]),
            resolve_stored_filename(task["task_id"], task["input_filename"], Path(task["task_dir"])),
            task["backend"],
        )
        return task, output_files

    @app.get("/stats", response_model=QueueStatsWrapper)
    async def get_queue_stats(request: Request):
        """Get task queue statistics visible to the current caller."""
        principal = get_principal_from_request(request)
        task_service = get_task_service()
        visible_stats = task_service.get_queue_stats_for_principal(principal)
        stats = QueueStatsResponse(
            pending=visible_stats["pending"],
            processing=visible_stats["processing"],
            completed=visible_stats["completed"],
            failed=visible_stats["failed"],
            cancelled=visible_stats["cancelled"],
        )
        
        return QueueStatsWrapper(queue_stats=stats, total=stats.pending + stats.processing + stats.completed + stats.failed + stats.cancelled)
    
    # Mount admin API router (includes /admin/tasks, /admin/callers, etc.)
    # NOTE: Removed duplicate /admin/tasks endpoint that conflicted with admin_router
    
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

    @app.get("/tasks", response_model=TaskListResponse)
    async def list_tasks(
        request: Request,
        page: int = Query(default=1, ge=1, description="Page number, starting from 1"),
        size: int = Query(default=20, ge=1, le=100, description="Page size"),
        status: str = Query(default="", description="Optional task status filter"),
    ):
        """List tasks visible to the current caller with pagination."""
        try:
            if status and status not in {item.value for item in TaskStatus}:
                raise HTTPException(
                    400,
                    ErrorResponse(
                        status="error",
                        error="INVALID_STATUS",
                        message=f"Invalid task status: {status}",
                    ).model_dump(),
                )

            principal = get_principal_from_request(request)
            task_service = get_task_service()
            offset = (page - 1) * size
            total = task_service.count_tasks_for_principal(principal, status=status)
            tasks = task_service.get_tasks_for_principal(
                principal,
                status=status,
                limit=size,
                offset=offset,
            )

            return TaskListResponse(
                tasks=tasks,
                total=total,
                page=page,
                size=size,
                total_pages=(total + size - 1) // size if total else 0,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"List tasks error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())
    
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
        enable_postprocess: bool | None = Form(default=None),
        postprocess_rule_id: str = Form(default=None),
        postprocess_context_size: int = Form(default=None),
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
            
            logger.info(f"Received file upload for async task: {file.filename}")

            temp_path = save_upload_stream(file.file, file.filename)
            try:
                task_service = get_task_service()
                result = task_service.create_task_from_file(
                    source_path=temp_path,
                    file_name=file.filename,
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
                    postprocess_context_size=postprocess_context_size,
                    principal=principal,
                )
            finally:
                cleanup_temp_file(temp_path)
            
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
            postprocessed_markdown = None
            error = task_data.get('error')
            # 后处理状态派生自最新 run；无 run 时回退创建时语义
            latest_run = db.get_latest_postprocess_run(task_id)
            if latest_run:
                postprocess_status = latest_run["status"]
            elif task_data.get("enable_postprocess"):
                postprocess_status = "pending"
            else:
                postprocess_status = "not_enabled"
            from mineru_mcp.services.task_service import collect_postprocess_filenames
            postprocess_filenames = collect_postprocess_filenames(db, task_data)
            postprocess_output_filename = postprocess_filenames[0] if postprocess_filenames else None

            if status == TaskStatus.COMPLETED and return_md:
                from mineru_mcp.task_queue.file_manager import resolve_stored_filename
                output_files = file_manager.get_output_files(
                    Path(task_data['task_dir']),
                    resolve_stored_filename(task_data['task_id'], task_data['input_filename'], Path(task_data['task_dir'])),
                    task_data['backend']
                )
                markdown = await asyncio.to_thread(file_manager.get_markdown_content, output_files['md'])
                # 多 run/多步骤下取第一个已存在的后处理产物作为详情正文
                for filename in postprocess_filenames:
                    try:
                        postprocess_path = build_postprocess_output_path(output_files['md'], filename)
                    except ValueError as exc:
                        # Degrade gracefully for historical tasks with dirty
                        # filenames so the detail endpoint does not 500.
                        logger.warning(
                            "Invalid postprocess output filename for task %s: %s", task_id, exc
                        )
                        continue
                    if postprocess_path.exists():
                        postprocessed_markdown = await asyncio.to_thread(
                            postprocess_path.read_text, encoding='utf-8'
                        )
                        postprocess_output_filename = filename
                        break
            
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
                postprocess_status=postprocess_status,
                postprocessed_markdown=postprocessed_markdown,
                postprocess_output_filename=postprocess_output_filename,
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
                error_code = result.get("error_code") or result.get("status")
                http_status = 404 if error_code == "ARTIFACT_NOT_AVAILABLE" else 400
                raise HTTPException(http_status, ErrorResponse(status="error", error=error_code, message=result.get("error", "Task not completed")).model_dump())

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
    
    @app.get("/postprocess-plans")
    async def list_public_postprocess_plans(request: Request):
        """List enabled postprocess plans available for manual postprocess runs."""
        try:
            get_principal_from_request(request)
            task_service = get_task_service()
            return {"items": task_service.list_enabled_postprocess_plans()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"List postprocess plans error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/tasks/{task_id}/postprocess-runs")
    async def create_postprocess_run(request: Request, task_id: str):
        """Manually trigger a postprocess run on a completed task.

        Body: {"plan_id": "ppp-..."}. The run executes asynchronously;
        poll GET /tasks/{task_id}/postprocess-runs for status.
        """
        try:
            principal = get_principal_from_request(request)
            body = await request.json()
            plan_id = (body or {}).get("plan_id")
            if not plan_id:
                raise HTTPException(400, ErrorResponse(status="error", error="INVALID_POSTPROCESS_PLAN", message="plan_id is required").model_dump())

            task_service = get_task_service()
            result = task_service.run_postprocess_authorized(task_id, plan_id, principal)

            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            if result.get("status") == "error":
                error_msg = result.get("error", "")
                if (
                    "not configured" in error_msg
                    or "configuration is incomplete" in error_msg
                ):
                    raise HTTPException(400, ErrorResponse(status="error", error="POSTPROCESS_LLM_NOT_CONFIGURED", message=error_msg).model_dump())
                if "status is" in error_msg:
                    raise HTTPException(409, ErrorResponse(status="error", error="TASK_NOT_COMPLETED", message=error_msg).model_dump())
                raise HTTPException(400, ErrorResponse(status="error", error="INVALID_POSTPROCESS_PLAN", message=error_msg).model_dump())

            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Create postprocess run error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.get("/tasks/{task_id}/postprocess-runs")
    async def list_postprocess_runs(request: Request, task_id: str):
        """List postprocess runs (with per-step status) for a task."""
        try:
            principal = get_principal_from_request(request)
            task_service = get_task_service()
            result = task_service.list_postprocess_runs_authorized(task_id, principal)

            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="TASK_NOT_FOUND", message="Task not found").model_dump())
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"List postprocess runs error: {e}")
            err = from_exception(e)
            raise HTTPException(err.http_status, err.to_dict())

    @app.post("/postprocess-runs/{run_id}/cancel")
    async def cancel_postprocess_run(request: Request, run_id: str):
        """Cancel a pending or running postprocess run."""
        try:
            principal = get_principal_from_request(request)
            task_service = get_task_service()
            result = task_service.cancel_postprocess_run_authorized(run_id, principal)

            if result.get("status") == "not_found":
                raise HTTPException(404, ErrorResponse(status="error", error="RUN_NOT_FOUND", message="Run not found").model_dump())
            if not result.get("cancelled"):
                raise HTTPException(409, ErrorResponse(status="error", error="RUN_NOT_CANCELLABLE", message="Run is not in a cancellable state").model_dump())
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Cancel postprocess run error: {e}")
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

    # Mount admin API router
    app.include_router(admin_router)
    
    return app
