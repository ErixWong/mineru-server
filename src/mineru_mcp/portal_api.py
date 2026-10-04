"""用户门户 API：以共享 session cookie 读取个人资料、额度和任务。"""

import asyncio
import base64
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from loguru import logger
from starlette.responses import Response

from mineru_mcp.admin_auth import get_current_admin, verify_session
from mineru_mcp.admin_api import require_csrf_token, require_same_origin
from mineru_mcp.config import get_config
from mineru_mcp.errors import ErrorCode, from_exception
from mineru_mcp.models import TaskStatus
from mineru_mcp.postprocess import build_postprocess_output_path
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import get_task_service
from mineru_mcp.services.task_service import collect_postprocess_filenames
from mineru_mcp.task_queue import TaskDatabase
from mineru_mcp.task_queue.file_manager import resolve_stored_filename
from mineru_mcp.utils import cleanup_temp_file, save_upload_stream


router = APIRouter(prefix="/portal", tags=["portal"])


def _require_portal_principal(request: Request) -> CurrentPrincipal:
    """校验共享 session，并将门户账号约束为仅可访问自身资源。"""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Not logged in"})
    session = verify_session(session_token)
    if not session:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session expired or invalid"})
    account = get_current_admin(session_token)
    if not account:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session account is unavailable"})
    if account.role not in {"user", "admin"} or not account.user_id:
        raise HTTPException(403, {"status": "error", "error": "FORBIDDEN", "message": "Portal account required"})
    if account.must_change_password:
        raise HTTPException(
            403,
            {"status": "error", "error": "PASSWORD_CHANGE_REQUIRED", "message": "Change your password before using the portal"},
        )
    if not account.caller_id:
        raise HTTPException(409, {"status": "error", "error": "CALLER_NOT_FOUND", "message": "User has no linked caller"})

    principal = CurrentPrincipal(
        principal_id=account.user_id,
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name=account.display_name,
        caller_id=account.caller_id,
        user_id=account.user_id,
    )
    return principal


def _get_db() -> TaskDatabase:
    return TaskDatabase(db_path=get_config().db_path)


@router.get("/me")
async def get_portal_me(request: Request):
    """返回当前账号资料及其 caller 台账中的额度余额。"""
    principal = _require_portal_principal(request)
    db = _get_db()
    user = db.get_user(principal.user_id)
    caller = db.get_user_caller(principal.user_id)
    if not user or not caller:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "User not found"})

    total = caller.get("quota_total_pages")
    remaining = db.get_quota_balance(principal.caller_id)
    used = max(0, int(total) - int(remaining)) if total is not None and remaining is not None else None
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "must_change_password": bool(user["must_change_password"]),
        "caller_id": principal.caller_id,
        "api_key_prefix": caller.get("api_key_prefix"),
        "quota_total_pages": total,
        "quota_used_pages": used,
        "quota_remaining_pages": remaining,
        "created_at": user["created_at"],
    }


@router.get("/quota/ledger")
async def get_portal_quota_ledger(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """分页读取当前账号的配额流水。"""
    principal = _require_portal_principal(request)
    db = _get_db()
    total = db.count(
        "SELECT COUNT(*) FROM quota_ledger WHERE caller_id = ?",
        (principal.caller_id,),
    )
    return {
        "items": db.list_quota_ledger(principal.caller_id, size, (page - 1) * size),
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if total else 0,
    }


@router.get("/tasks")
async def list_portal_tasks(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: str = "",
):
    """分页列出当前用户拥有的任务。"""
    principal = _require_portal_principal(request)
    if status and status not in {item.value for item in TaskStatus}:
        raise HTTPException(400, {"status": "error", "error": "INVALID_STATUS", "message": f"Invalid task status: {status}"})

    service = get_task_service()
    offset = (page - 1) * size
    total = service.count_tasks_for_principal(principal, status=status)
    tasks = service.get_tasks_for_principal(principal, status=status, limit=size, offset=offset)
    return {
        "tasks": tasks,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if total else 0,
    }


@router.get("/tasks/{task_id}")
async def get_portal_task(request: Request, task_id: str):
    """读取当前用户任务状态；不存在或不归本人时均返回 404。"""
    principal = _require_portal_principal(request)
    service = get_task_service()
    result = service.get_task_status_authorized(task_id, principal)
    if result.get("status") == "not_found":
        raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})
    task = service.db.get_task(task_id)
    return {**result, "input_filename": task["input_filename"]} if task else result


@router.post("/tasks")
async def create_portal_task(
    request: Request,
    file: UploadFile = File(...),
    backend: str | None = Form(default=None),
    lang: str = Form(default="ch"),
    formula_enable: bool = Form(default=True),
    table_enable: bool = Form(default=True),
    image_analysis: bool = Form(default=True),
    start_page_id: int = Form(default=0),
    end_page_id: int = Form(default=99999),
):
    """通过当前用户关联的 caller 提交文件，额度预扣由任务服务统一完成。"""
    principal = _require_portal_principal(request)
    session = verify_session(request.cookies.get("admin_session", ""))
    if not session:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session expired or invalid"})
    require_same_origin(request)
    require_csrf_token(request, session)
    try:
        temp_path = save_upload_stream(file.file, file.filename)
        try:
            result = get_task_service().create_task_from_file(
                source_path=temp_path,
                file_name=file.filename,
                backend=backend or None,
                lang=lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                principal=principal,
            )
        finally:
            cleanup_temp_file(temp_path)
        return {
            "status": "ok",
            "task_id": result["task_id"],
            "message": "任务已提交",
        }
    except HTTPException:
        raise
    except Exception as exc:
        error = from_exception(exc)
        payload = error.to_dict()
        if error.code == ErrorCode.QUOTA_EXCEEDED:
            remaining = int((error.details or {}).get("remaining_pages", 0))
            requested = int((error.details or {}).get("requested_pages", 0))
            payload["message"] = f"额度不足：剩余 {remaining} 页，本次需要 {requested} 页。请补充额度或缩小页码范围后重试。"
        logger.warning("Portal task submission failed: {}", error)
        raise HTTPException(error.http_status, payload) from exc


@router.get("/tasks/{task_id}/deliverables")
async def list_portal_task_deliverables(request: Request, task_id: str):
    """列出当前用户任务的交付物。"""
    principal = _require_portal_principal(request)
    result = get_task_service().list_deliverables_authorized(task_id, principal)
    if result.get("status") == "not_found":
        raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})
    return result


@router.get("/tasks/{task_id}/deliverables/download")
async def download_portal_task_deliverable(
    request: Request,
    task_id: str,
    download_key: str = Query(...),
):
    """下载当前用户任务中公开的交付物。"""
    principal = _require_portal_principal(request)
    try:
        result = get_task_service().download_deliverable_authorized(
            task_id,
            download_key,
            include_content=True,
            principal=principal,
        )
        if result.get("status") == "not_found":
            raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})
        if result.get("status") != "completed":
            error_code = result.get("error_code") or result.get("status")
            status_code = 404 if error_code in {"ARTIFACT_NOT_AVAILABLE", "INVALID_DOWNLOAD_KEY"} else 409
            raise HTTPException(
                status_code,
                {"status": "error", "error": error_code, "message": result.get("error", "交付物暂不可用")},
            )

        if result.get("encoding") == "utf-8":
            content = result.get("content", "")
        elif result.get("encoding") == "json":
            content = result.get("content", "")
        else:
            content = base64.b64decode(result.get("content", ""))

        filename = quote(result.get("filename", "deliverable"), safe="")
        return Response(
            content=content,
            media_type=result.get("media_type", "text/markdown" if result.get("encoding") == "utf-8" else "application/octet-stream"),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "Cache-Control": "no-store",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        error = from_exception(exc)
        logger.error("Portal deliverable download failed: {}", error)
        raise HTTPException(error.http_status, error.to_dict()) from exc


@router.get("/tasks/{task_id}/result")
async def get_portal_task_result(request: Request, task_id: str):
    """读取本人任务的 Markdown 正文，未完成时只返回状态信息。"""
    principal = _require_portal_principal(request)
    service = get_task_service()
    result = service.get_task_status_authorized(task_id, principal)
    if result.get("status") == "not_found":
        raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})
    if result.get("status") != TaskStatus.COMPLETED.value:
        return {**result, "markdown": None, "postprocessed_markdown": None}

    task = service.db.get_task(task_id)
    if task is None:
        raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})

    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], Path(task["task_dir"]))
    output_files = service.file_manager.get_output_files(
        Path(task["task_dir"]),
        stored_name,
        task["backend"],
    )
    markdown = await asyncio.to_thread(service.file_manager.get_markdown_content, output_files["md"])
    postprocessed_markdown = None
    for filename in collect_postprocess_filenames(service.db, task):
        try:
            postprocess_path = build_postprocess_output_path(output_files["md"], filename)
        except ValueError as exc:
            logger.warning("Invalid postprocess output filename for task %s: %s", task_id, exc)
            continue
        if postprocess_path.exists():
            postprocessed_markdown = await asyncio.to_thread(postprocess_path.read_text, encoding="utf-8")
            break

    return {
        **result,
        "markdown": markdown,
        "postprocessed_markdown": postprocessed_markdown,
    }
