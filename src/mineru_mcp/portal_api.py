"""用户门户 API：以共享 session cookie 读取个人资料、额度和任务。"""

from fastapi import APIRouter, HTTPException, Query, Request

from mineru_mcp.admin_auth import get_current_admin, verify_session
from mineru_mcp.config import get_config
from mineru_mcp.models import TaskStatus
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import get_task_service
from mineru_mcp.task_queue import TaskDatabase


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
    result = get_task_service().get_task_status_authorized(task_id, principal)
    if result.get("status") == "not_found":
        raise HTTPException(404, {"status": "error", "error": "TASK_NOT_FOUND", "message": "Task not found"})
    return result
