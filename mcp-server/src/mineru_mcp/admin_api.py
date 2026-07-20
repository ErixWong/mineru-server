"""
Admin API Module

REST API endpoints for admin console management.
Provides admin authentication, caller management, task viewing, and settings.
"""

import os
import base64
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Response, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.postprocess import normalize_output_filename
from mineru_mcp.errors import from_exception
from mineru_mcp.task_queue import TaskDatabase
from mineru_mcp.task_queue.database import UNSET
from mineru_mcp.admin_auth import (
    admin_login,
    admin_logout,
    admin_change_password,
    verify_session,
    get_current_admin,
    invalidate_all_sessions,
    get_default_admin_username,
    get_default_admin_password,
)
from mineru_mcp.auth import generate_token
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.validation import validate_upload_file


# Initialize router
router = APIRouter(prefix="/admin", tags=["admin"])


def _get_db() -> TaskDatabase:
    """Get database instance."""
    config = get_config()
    return TaskDatabase(db_path=config.db_path)


# ========== Request/Response Models ==========

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CallerCreateRequest(BaseModel):
    name: str
    expires_at: Optional[str] = None
    default_postprocess_rule_id: Optional[str] = None


class CallerUpdateRequest(BaseModel):
    name: Optional[str] = None
    disabled: Optional[bool] = None
    expires_at: Optional[str] = None
    default_postprocess_rule_id: Optional[str] = None


class TaskFilterRequest(BaseModel):
    caller_id: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    key: Optional[str] = None
    task_id: Optional[str] = None
    limit: int = 50


class PostprocessRuleCreateRequest(BaseModel):
    title: str
    prompt: str
    output_filename: str
    enabled: bool = True


class PostprocessRuleUpdateRequest(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    output_filename: Optional[str] = None
    enabled: Optional[bool] = None


# ========== Auth Middleware Helper ==========

# Paths that don't require password change
_PASSWORD_CHANGE_EXEMPT_PATHS = {"/api/admin/change-password", "/api/admin/me", "/api/admin/logout", "/api/admin/login"}


def _request_is_secure(request: Request) -> bool:
    """Determine whether response cookies should be marked secure."""
    if request.url.scheme == "https":
        return True

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto.lower() == "https":
        return True

    forwarded = request.headers.get("forwarded", "")
    if "proto=https" in forwarded.lower():
        return True

    return False


def require_admin_session(request: Request) -> dict:
    """Require valid admin session.
    
    Args:
        request: FastAPI request.
        
    Returns:
        Session data if valid.
        
    Raises:
        HTTPException: If session invalid or password change required.
    """
    cookies = request.cookies
    session_token = cookies.get("admin_session")
    if not session_token:
        logger.warning("require_admin_session: no session cookie")
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Not logged in"})
    
    session_data = verify_session(session_token)
    if not session_data:
        logger.warning("require_admin_session: session invalid")
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session expired or invalid"})
    
    # Check if password change is required
    admin = get_current_admin(session_token)
    if admin and admin.must_change_password:
        # Allow access only to password change and logout endpoints
        path = request.url.path if request.url else ""
        if path not in _PASSWORD_CHANGE_EXEMPT_PATHS:
            logger.warning("require_admin_session: password change required")
            raise HTTPException(403, {"status": "error", "error": "PASSWORD_CHANGE_REQUIRED", "message": "You must change your password before accessing other features"})
    
    return session_data


def require_same_origin(request: Request) -> None:
    """Require unsafe admin requests to originate from the same origin.
    
    This is a lightweight CSRF mitigation for browser-based admin actions.
    Can be disabled entirely via MINERU_ADMIN_SAME_ORIGIN_CHECK=false (the
    CSRF token check still applies, but browser-origin protection is lost).
    """
    if os.getenv("MINERU_ADMIN_SAME_ORIGIN_CHECK", "true").lower() != "true":
        return

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    trust_proxy_headers = os.getenv("MINERU_ADMIN_TRUST_PROXY_HEADERS", "false").lower() == "true"

    forwarded_proto = None
    forwarded_host = None
    if trust_proxy_headers:
        forwarded = request.headers.get("forwarded", "")
        if forwarded:
            first_hop = forwarded.split(",", 1)[0]
            for part in first_hop.split(";"):
                key, sep, value = part.strip().partition("=")
                if not sep:
                    continue
                normalized_key = key.lower()
                normalized_value = value.strip().strip('"')
                if normalized_key == "proto" and normalized_value:
                    forwarded_proto = normalized_value
                elif normalized_key == "host" and normalized_value:
                    forwarded_host = normalized_value

    # Note: keep the conditional expressions parenthesized. Without the
    # parens, Python binds the trailing `or` chain into the else-branch of the
    # ternary, so a missing header crashes with AttributeError on .split().
    forwarded_proto_header = request.headers.get("x-forwarded-proto") if trust_proxy_headers else None
    forwarded_host_header = request.headers.get("x-forwarded-host") if trust_proxy_headers else None
    expected_scheme = (
        forwarded_proto_header
        or forwarded_proto
        or request.url.scheme
    ).split(",", 1)[0].strip()
    expected_host = (
        forwarded_host_header
        or forwarded_host
        or request.headers.get("host")
        or request.url.netloc
    ).split(",", 1)[0].strip()
    expected_origin = f"{expected_scheme}://{expected_host}"

    allowed_origins = {
        expected_origin,
        *{
            item.strip()
            for item in os.getenv("MINERU_ADMIN_ALLOWED_ORIGINS", "http://127.0.0.1:5180,http://localhost:5180").split(",")
            if item.strip()
        },
    }

    if referer:
        parsed_referer = urlsplit(referer)
        referer_origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}" if parsed_referer.scheme and parsed_referer.netloc else ""
    else:
        referer_origin = ""

    if origin and origin not in allowed_origins:
        logger.warning(f"Rejected admin request due to origin mismatch: {origin}")
        raise HTTPException(403, {"status": "error", "error": "FORBIDDEN", "message": "Cross-origin admin request blocked"})

    if not origin and referer_origin and referer_origin not in allowed_origins:
        logger.warning(f"Rejected admin request due to referer mismatch: {referer}")
        raise HTTPException(403, {"status": "error", "error": "FORBIDDEN", "message": "Cross-origin admin request blocked"})


def require_csrf_token(request: Request, session_data: dict) -> None:
    """Require a valid CSRF token for admin write operations."""
    expected = session_data.get("csrf_token")
    header_token = request.headers.get("x-csrf-token", "")
    cookie_token = request.cookies.get("admin_csrf", "")

    if not expected or not header_token or not cookie_token:
        raise HTTPException(403, {"status": "error", "error": "CSRF_REQUIRED", "message": "Missing CSRF token"})

    if not (secrets.compare_digest(header_token, expected) and secrets.compare_digest(cookie_token, expected)):
        raise HTTPException(403, {"status": "error", "error": "CSRF_INVALID", "message": "Invalid CSRF token"})


def require_admin_write_access(request: Request) -> dict:
    """Require authenticated admin session plus same-origin checks."""
    session = require_admin_session(request)
    require_same_origin(request)
    require_csrf_token(request, session)
    return session


def get_admin_user(request: Request) -> dict:
    """Get current admin user from session.
    
    Args:
        request: FastAPI request.
        
    Returns:
        Admin user info.
        
    Raises:
        HTTPException: If not logged in.
    """
    session_token = request.cookies.get("admin_session")
    if not session_token:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Not logged in"})
    
    admin = get_current_admin(session_token)
    if not admin:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session expired or invalid"})
    
    return {"username": admin.username, "must_change_password": admin.must_change_password}


# ========== Auth Endpoints ==========

@router.post("/login")
async def login(request: Request, login_req: LoginRequest):
    """Admin login endpoint."""
    try:
        result = admin_login(login_req.username, login_req.password)

        is_secure = _request_is_secure(request)
        
        response = JSONResponse({
            "success": True,
            "message": "Login successful",
            "must_change_password": result["must_change_password"],
            "username": result["username"],
        })
        
        # Set session cookie with security flags
        response.set_cookie(
            key="admin_session",
            value=result["session_token"],
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax",
            secure=is_secure,
            path="/",
        )
        response.set_cookie(
            key="admin_csrf",
            value=result["csrf_token"],
            httponly=False,
            max_age=86400,
            samesite="strict",
            secure=is_secure,
            path="/",
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(401, {"status": "error", "error": "AUTH_FAILED", "message": str(e)})
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        raise HTTPException(500, {"status": "error", "error": "INTERNAL_ERROR", "message": "Login failed"})


@router.post("/logout")
async def logout(request: Request):
    """Admin logout endpoint."""
    require_same_origin(request)
    session_token = request.cookies.get("admin_session")
    
    if session_token:
        admin_logout(session_token)
    
    response = JSONResponse({"success": True, "message": "Logged out"})
    response.delete_cookie("admin_session")
    response.delete_cookie("admin_csrf")
    return response


@router.post("/change-password")
async def change_password(request: Request, pw_req: ChangePasswordRequest):
    """Change admin password."""
    require_same_origin(request)
    # Require authentication
    session_token = request.cookies.get("admin_session")
    if not session_token:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Not logged in"})
    
    session_data = verify_session(session_token)
    if not session_data:
        raise HTTPException(401, {"status": "error", "error": "UNAUTHORIZED", "message": "Session expired"})
    require_csrf_token(request, session_data)
    
    username = session_data["username"]
    
    try:
        result = admin_change_password(username, pw_req.old_password, pw_req.new_password)
        
        # Invalidate all other sessions after password change
        invalidate_all_sessions(username)
        
        return {"success": True, "message": "Password changed successfully"}
        
    except ValueError as e:
        raise HTTPException(400, {"status": "error", "error": "PASSWORD_CHANGE_FAILED", "message": str(e)})


@router.get("/me")
async def get_current_user(request: Request):
    """Get current admin user info."""
    try:
        admin = get_admin_user(request)
        return {
            "username": admin["username"],
            "must_change_password": admin["must_change_password"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(500, {"status": "error", "error": "INTERNAL_ERROR", "message": str(e)})


# ========== Caller Management Endpoints ==========

@router.get("/callers")
async def list_callers(request: Request, include_disabled: bool = False):
    """List all callers."""
    require_admin_session(request)
    
    db = _get_db()
    callers = db.list_callers(include_disabled=include_disabled)
    
    if not callers:
        return []
    
    # Add calculated fields (last 7 days stats) - optimized single query
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    
    # Get all caller IDs
    caller_ids = [c["caller_id"] for c in callers]
    
    # Single query to get stats for all callers
    placeholders = ",".join(["?"] * len(caller_ids))
    stats_query = f"""
        SELECT 
            caller_id,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM tasks 
        WHERE caller_id IN ({placeholders}) AND created_at >= ?
        GROUP BY caller_id
    """
    stats_params = tuple(caller_ids) + (week_ago,)
    stats_rows = db.fetch_all(stats_query, stats_params)
    
    # Build stats lookup
    stats_map = {row["caller_id"]: {"total": row["total"], "failed": row["failed"]} for row in stats_rows}
    
    result = []
    for caller in callers:
        caller_id = caller["caller_id"]
        stats = stats_map.get(caller_id, {"total": 0, "failed": 0})
        
        result.append({
            "caller_id": caller["caller_id"],
            "name": caller["name"],
            "api_key": caller["api_key"],
            "api_key_prefix": caller["api_key_prefix"],
            "api_key_suffix": caller["api_key_suffix"],
            "default_postprocess_rule_id": caller.get("default_postprocess_rule_id"),
            "expires_at": caller["expires_at"],
            "disabled": bool(caller["disabled"]),
            "last_used_at": caller["last_used_at"],
            "created_at": caller["created_at"],
            "stats_last_7_days": stats
        })
    
    return result


@router.post("/callers")
async def create_caller(request: Request, caller_req: CallerCreateRequest):
    """Create a new caller with API key."""
    require_admin_write_access(request)
    
    db = _get_db()
    if caller_req.default_postprocess_rule_id:
        rule = db.get_postprocess_rule(caller_req.default_postprocess_rule_id)
        if not rule or not int(rule.get("enabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_POSTPROCESS_RULE", "message": "Default postprocess rule not found or disabled"})
    
    # Generate API key
    api_key = generate_token(32)
    api_key_prefix = api_key[:8]
    api_key_suffix = api_key[-4:]
    
    # Generate caller_id
    caller_id = secrets.token_hex(8)
    
    # Create caller
    db.create_caller(
        caller_id=caller_id,
        name=caller_req.name,
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        api_key_suffix=api_key_suffix,
        default_postprocess_rule_id=caller_req.default_postprocess_rule_id,
        expires_at=caller_req.expires_at,
    )
    
    logger.info(f"Created caller: {caller_id} ({caller_req.name})")
    
    return {
        "caller_id": caller_id,
        "name": caller_req.name,
        "api_key": api_key,  # Only returned once!
        "default_postprocess_rule_id": caller_req.default_postprocess_rule_id,
        "expires_at": caller_req.expires_at,
    }


@router.patch("/callers/{caller_id}")
async def update_caller(request: Request, caller_id: str, caller_req: CallerUpdateRequest):
    """Update caller info."""
    require_admin_write_access(request)
    
    db = _get_db()
    
    # Check if caller exists
    caller = db.get_caller(caller_id)
    if not caller:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Caller not found"})

    default_rule_id = caller_req.default_postprocess_rule_id
    if default_rule_id == "":
        default_rule_id = None
    elif default_rule_id:
        rule = db.get_postprocess_rule(default_rule_id)
        if not rule or not int(rule.get("enabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_POSTPROCESS_RULE", "message": "Default postprocess rule not found or disabled"})
    
    # Update fields
    updated = db.update_caller(
        caller_id=caller_id,
        name=caller_req.name,
        disabled=caller_req.disabled,
        default_postprocess_rule_id=default_rule_id if caller_req.default_postprocess_rule_id is not None else UNSET,
        expires_at=caller_req.expires_at,
    )
    
    if not updated:
        raise HTTPException(500, {"status": "error", "error": "UPDATE_FAILED", "message": "Failed to update caller"})
    
    return {"success": True, "message": "Caller updated"}


@router.post("/callers/{caller_id}/reset-key")
async def reset_caller_key(request: Request, caller_id: str):
    """Reset a caller's API key."""
    require_admin_write_access(request)
    
    db = _get_db()
    
    # Check if caller exists
    caller = db.get_caller(caller_id)
    if not caller:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Caller not found"})
    
    # Generate new API key
    api_key = generate_token(32)
    api_key_prefix = api_key[:8]
    api_key_suffix = api_key[-4:]
    
    # Reset key
    updated = db.reset_caller_key(
        caller_id=caller_id,
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        api_key_suffix=api_key_suffix,
    )
    
    if not updated:
        raise HTTPException(500, {"status": "error", "error": "RESET_FAILED", "message": "Failed to reset API key"})
    
    logger.info(f"Reset API key for caller: {caller_id}")
    
    return {
        "caller_id": caller_id,
        "api_key": api_key,  # Only returned once!
    }


@router.delete("/callers/{caller_id}")
async def delete_caller(request: Request, caller_id: str):
    """Delete a caller."""
    require_admin_write_access(request)
    
    db = _get_db()
    
    # Check if caller exists
    caller = db.get_caller(caller_id)
    if not caller:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Caller not found"})
    
    # Delete caller
    deleted = db.delete_caller(caller_id)
    
    if not deleted:
        raise HTTPException(500, {"status": "error", "error": "DELETE_FAILED", "message": "Failed to delete caller"})
    
    logger.info(f"Deleted caller: {caller_id}")
    
    return {"success": True, "message": "Caller deleted"}


# ========== Task Management Endpoints ==========

@router.get("/tasks")
async def list_tasks(
    request: Request,
    caller_id: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    key: str = "",
    task_id: str = "",
    limit: int = 50,
    offset: int = 0,
):
    """List tasks with filters."""
    require_admin_session(request)
    
    db = _get_db()
    
    # Build query
    conditions = []
    params = []
    
    if caller_id:
        conditions.append("caller_id = ?")
        params.append(caller_id)
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    
    if start_date:
        # Extend start_date to beginning of day
        start_datetime = start_date + "T00:00:00"
        conditions.append("created_at >= ?")
        params.append(start_datetime)
    
    if end_date:
        # Extend end_date to end of day to include all tasks on that day
        end_datetime = end_date + "T23:59:59.999999"
        conditions.append("created_at <= ?")
        params.append(end_datetime)
    
    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)
    
    # Key filtering: look up caller by API key
    if key:
        caller_by_key = db.get_caller_by_api_key(key)
        if caller_by_key:
            conditions.append("caller_id = ?")
            params.append(caller_by_key["caller_id"])
        else:
            # If key provided but not found, return empty result
            return {
                "tasks": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
            }
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Get total count
    total = db.count(f"SELECT COUNT(*) FROM tasks WHERE {where_clause}", tuple(params))
    
    # Get tasks
    params.append(limit)
    params.append(offset)
    
    tasks = db.fetch_all(f"""
        SELECT * FROM tasks 
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, tuple(params))
    
    # Pre-fetch caller info - optimized single query
    caller_ids = [task["caller_id"] for task in tasks if task.get("caller_id")]
    callers_map = {}
    if caller_ids:
        placeholders = ",".join(["?"] * len(caller_ids))
        callers = db.fetch_all(f"SELECT caller_id, name, api_key_suffix FROM callers WHERE caller_id IN ({placeholders})", tuple(caller_ids))
        callers_map = {c["caller_id"]: c for c in callers}
    
    # Enrich with caller info
    result = []
    for task in tasks:
        caller = callers_map.get(task.get("caller_id")) if task.get("caller_id") else None
        
        result.append({
            "task_id": task["task_id"],
            "status": task["status"],
            "progress": task.get("progress", 0),
            "message": task.get("message"),
            "created_at": task["created_at"],
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "error": task.get("error"),
            "input_filename": task["input_filename"],
            "caller_id": task.get("caller_id"),
            "caller_name": caller["name"] if caller else None,
            "api_key_suffix": caller["api_key_suffix"] if caller else None,
            "result_summary": task.get("result_summary"),
            "enable_postprocess": bool(task.get("enable_postprocess", 0)),
            "postprocess_status": task.get("postprocess_status"),
        })
    
    return {
        "tasks": result,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tasks")
async def create_task(
    request: Request,
    file: UploadFile = File(...),
    backend: str = Form(default=None),
    lang: str = Form(default="ch"),
    enable_postprocess: bool | None = Form(default=None),
    postprocess_rule_id: Optional[str] = Form(default=None),
    postprocess_context_size: Optional[int] = Form(default=None),
):
    """Create a new task from admin console."""
    require_admin_write_access(request)
    try:
        # Read file bytes
        file_bytes = await file.read()
        safe_display_name = validate_upload_file(file.filename, file_bytes)
        file_b64 = base64.b64encode(file_bytes).decode()
        
        from mineru_mcp.services import get_task_service
        task_service = get_task_service()
        
        result = task_service.create_task_from_base64(
            file_base64=file_b64,
            file_name=safe_display_name,
            backend=backend if backend else None,
            lang=lang,
            enable_postprocess=enable_postprocess,
            postprocess_rule_id=postprocess_rule_id,
            postprocess_context_size=postprocess_context_size,
            principal=CurrentPrincipal(
                principal_id="admin-console",
                principal_type=PrincipalType.SINGLE_USER,
                role=PrincipalRole.ADMIN,
                display_name="Admin Console",
            ),
        )
        
        # Preserve original filename for source download (sanitized only)
        if file.filename:
            db = _get_db()
            task = db.get_task(result["task_id"])
            if task:
                task_dir = Path(task["task_dir"])
                old_name = task["input_filename"]
                new_name = safe_display_name
                old_path = task_dir / old_name
                new_path = task_dir / new_name
                if old_path.exists() and old_name != new_name:
                    old_path.rename(new_path)
                db.execute("UPDATE tasks SET input_filename = ? WHERE task_id = ?", (new_name, result["task_id"]))
        
        return {
            "status": "ok",
            "task_id": result["task_id"],
            "message": "Task created",
        }
    except Exception as e:
        logger.error(f"Admin create task error: {e}")
        err = from_exception(e)
        raise HTTPException(err.http_status, err.to_dict())


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    """Delete a task."""
    require_admin_write_access(request)

    from mineru_mcp.models import TaskStatus

    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    status = TaskStatus(task["status"])
    if status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(
            409,
            {"status": "error", "error": "TASK_NOT_TERMINAL", "message": "Task is still running"},
        )

    task_dir = Path(task["task_dir"])
    from mineru_mcp.task_queue import FileManager
    file_manager = FileManager(output_root=get_config().output_root)
    file_manager.cleanup_task_dir(task_dir)
    deleted = db.delete_task(task_id)
    
    if not deleted:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    
    logger.info(f"Deleted task: {task_id}")
    return {"status": "ok", "message": "Task deleted"}


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    """Get task details."""
    require_admin_session(request)
    
    db = _get_db()
    
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    
    # Get caller info
    caller = None
    if task.get("caller_id"):
        caller = db.get_caller(task["caller_id"])
    
    # Get raw result for completed tasks
    result_raw = None
    if task.get("status") == "completed":
        try:
            from mineru_mcp.task_queue import FileManager

            file_manager = FileManager(output_root=get_config().output_root)
            output_files = file_manager.get_output_files(
                Path(task["task_dir"]),
                task["input_filename"],
                task["backend"],
            )
            result_raw = file_manager.get_markdown_content(output_files["md"])
        except Exception as e:
            logger.warning(f"Failed to get result for task {task_id}: {e}")
    
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task.get("progress", 0),
        "message": task.get("message"),
        "error": task.get("error"),
        "created_at": task["created_at"],
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "input_filename": task["input_filename"],
        "task_dir": task["task_dir"],
        "backend": task.get("backend"),
        "caller_id": task.get("caller_id"),
        "caller_name": caller["name"] if caller else None,
        "api_key_suffix": caller["api_key_suffix"] if caller else None,
        "request_summary": task.get("request_summary"),
        "result_summary": task.get("result_summary"),
        "result_raw": result_raw,
        "enable_postprocess": bool(task.get("enable_postprocess", 0)),
        "postprocess_status": task.get("postprocess_status"),
    }


@router.get("/tasks/{task_id}/deliverables")
async def list_task_deliverables(request: Request, task_id: str):
    """List task deliverables."""
    require_admin_session(request)
    
    from mineru_mcp.models import TaskStatus
    from mineru_mcp.services import get_task_service
    
    db = _get_db()
    task_service = get_task_service()
    
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    
    status = TaskStatus(task["status"])

    # Parse outputs are on disk and validated as soon as the parsing stage
    # finishes, which is signalled by postprocess_status entering "processing"
    # (see task_queue/processor.py). Expose them immediately instead of
    # waiting for postprocess to finish and the task to complete.
    # The main status must also be "processing": recover_processing_tasks()
    # resets status to "pending" without touching postprocess_status, so a
    # crash-recovered task re-queued for a fresh run must not serve the
    # previous attempt's files while they are about to be overwritten.
    parse_stage_done = status == TaskStatus.COMPLETED or (
        task.get("postprocess_status") == "processing" and task["status"] == "processing"
    )

    if not parse_stage_done:
        return {
            "task_id": task_id,
            "status": status.value,
            "artifacts": [],
        }

    if status == TaskStatus.COMPLETED:
        # Use TaskService.list_deliverables() to get unified artifact structure
        result = task_service.list_deliverables(task_id)
        artifact_items = result.get("artifacts", [])
    else:
        # Postprocess still running: TaskService guards to completed-only, so
        # enumerate artifacts directly. Files that do not exist yet (e.g. the
        # postprocess output) are marked unavailable and carry no download_key.
        artifact_items = task_service.file_manager.list_task_artifacts(
            Path(task["task_dir"]),
            task["input_filename"],
            task["backend"],
            task.get("postprocess_output_filename"),
        )
    
    # Get actual file sizes
    from mineru_mcp.task_queue import FileManager
    config = get_config()
    fm = FileManager(output_root=config.output_root)
    task_dir = Path(task["task_dir"])
    
    artifacts = []
    for artifact in artifact_items:
        size = None
        try:
            dk = artifact.get("download_key")
            if dk:
                file_path = fm.resolve_download_key(task_dir, dk)
                if file_path.exists():
                    size = file_path.stat().st_size
        except Exception:
            pass
        artifacts.append({
            "name": artifact.get("name"),
            "filename": artifact.get("filename"),
            "download_key": artifact.get("download_key"),
            "size": size,
            "artifact_type": artifact.get("artifact_type"),
            "role": artifact.get("role"),
            "available": artifact.get("available", False),
            "is_default": artifact.get("is_default", False),
        })
    
    return {
        "task_id": task_id,
        "status": status.value,
        "artifacts": artifacts,
    }


@router.get("/tasks/{task_id}/deliverables/download")
async def download_task_deliverable(request: Request, task_id: str, download_key: str, inline: bool = False):
    """Download a task deliverable."""
    require_admin_session(request)
    
    from starlette.responses import FileResponse
    from mineru_mcp.task_queue import FileManager
    
    config = get_config()
    db = _get_db()
    file_manager = FileManager(output_root=config.output_root)
    
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    # Serve files once the parsing stage is done (task completed, or
    # postprocess running). Unlike the public/MCP path in
    # task_service.download_deliverable, the admin console may access parse
    # outputs before the whole task completes. The allowed-keys check below
    # only exposes files that already exist, so unfinished artifacts (e.g.
    # the postprocess output) stay inaccessible. The "processing" main-status
    # requirement excludes crash-recovered tasks (see list endpoint above).
    parse_stage_done = task["status"] == "completed" or (
        task.get("postprocess_status") == "processing" and task["status"] == "processing"
    )
    if not parse_stage_done:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task is not completed"})

    task_dir = Path(task["task_dir"])

    # Security: validate download_key using the unified contract
    # 1. Resolve the download_key to a candidate path
    try:
        file_path = file_manager.resolve_download_key(task_dir, download_key)
    except ValueError:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Invalid download key"})
    
    # 2. Check if the key is in the allowed set for this task
    allowed_keys = file_manager.get_allowed_download_keys(
        task_dir,
        task["input_filename"],
        task["backend"],
        task.get("postprocess_output_filename"),
    )
    if download_key not in allowed_keys:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "File not found"})
    
    # 3. Verify the file actually exists
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "File not found"})
    
    media_type = file_manager.get_media_type_for_path(file_path)
    disposition = "inline" if inline else "attachment"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=file_path.name,
        content_disposition_type=disposition,
    )


@router.get("/tasks/{task_id}/source")
async def download_task_source(request: Request, task_id: str, name: str = ""):
    """Download the original source file for a task."""
    require_admin_session(request)
    
    from starlette.responses import FileResponse
    from mineru_mcp.task_queue import FileManager
    
    config = get_config()
    db = _get_db()
    file_manager = FileManager(output_root=config.output_root)
    
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    
    task_dir = Path(task["task_dir"])
    input_filename = task["input_filename"]
    source_path = task_dir / input_filename
    
    if not source_path.exists():
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Source file not found"})
    
    download_name = name if name else input_filename
    
    # Determine media type based on file extension
    suffix = source_path.suffix.lower()
    if suffix in (".pdf"):
        media_type = "application/pdf"
    elif suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_type = file_manager.get_image_mime_type(source_path)
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(source_path, media_type=media_type, filename=download_name)


# ========== Settings Endpoints ==========

@router.get("/settings/runtime")
async def get_runtime_settings(request: Request):
    """Get runtime configuration (read-only)."""
    require_admin_session(request)
    
    config = get_config()
    db = _get_db()
    
    # Get admin info
    from mineru_mcp.admin_auth import get_default_admin_username, verify_password
    admin_username = get_default_admin_username()
    admin = db.get_admin(admin_username)
    
    # Check if using default password using bcrypt-compatible comparison
    default_pw = get_default_admin_password()
    using_default_password = False
    if admin:
        using_default_password = verify_password(default_pw, admin["password_hash"])
    
    return {
        "max_concurrent": config.max_concurrent,
        "max_concurrent_source": "MINERU_MAX_CONCURRENT env var",
        "max_concurrent_note": "Modifying this value requires service restart",
        "admin_security": {
            "default_password_in_use": using_default_password,
            "default_username": admin_username,
            "password_change_required": admin["must_change_password"] == 1 if admin else True,
        },
    }


@router.get("/postprocess-rules")
async def list_postprocess_rules(request: Request, include_disabled: bool = True):
    require_admin_session(request)
    db = _get_db()
    return {
        "items": db.list_postprocess_rules(include_disabled=include_disabled),
        "default_context_size": get_config().postprocess_context_size,
    }


@router.post("/postprocess-rules")
async def create_postprocess_rule(request: Request, payload: PostprocessRuleCreateRequest):
    require_admin_write_access(request)
    db = _get_db()
    title = payload.title.strip()
    prompt = payload.prompt.strip()
    if not title:
        raise HTTPException(400, {"status": "error", "error": "INVALID_TITLE", "message": "Title is required"})
    if not prompt:
        raise HTTPException(400, {"status": "error", "error": "INVALID_PROMPT", "message": "Prompt is required"})
    try:
        output_filename = normalize_output_filename(payload.output_filename)
    except ValueError as exc:
        raise HTTPException(400, {"status": "error", "error": "INVALID_OUTPUT_FILENAME", "message": str(exc)})

    rule_id = f"ppr-{uuid.uuid4().hex[:12]}"
    db.create_postprocess_rule(rule_id, title, prompt, output_filename=output_filename, enabled=payload.enabled)
    return {"status": "ok", "rule_id": rule_id}


@router.put("/postprocess-rules/{rule_id}")
async def update_postprocess_rule(request: Request, rule_id: str, payload: PostprocessRuleUpdateRequest):
    require_admin_write_access(request)
    db = _get_db()
    if payload.enabled is False:
        caller_refs = db.count(
            "SELECT COUNT(*) FROM callers WHERE default_postprocess_rule_id = ?",
            (rule_id,),
        )
        if caller_refs > 0:
            raise HTTPException(409, {"status": "error", "error": "RULE_REFERENCED_BY_CALLERS", "message": "Rule is set as default postprocess rule by one or more callers"})
    normalized_output_filename = None
    if payload.output_filename is not None:
        try:
            normalized_output_filename = normalize_output_filename(payload.output_filename)
        except ValueError as exc:
            raise HTTPException(400, {"status": "error", "error": "INVALID_OUTPUT_FILENAME", "message": str(exc)})
    updated = db.update_postprocess_rule(
        rule_id,
        title=payload.title.strip() if payload.title is not None else None,
        prompt=payload.prompt.strip() if payload.prompt is not None else None,
        output_filename=normalized_output_filename,
        enabled=payload.enabled,
    )
    if not updated:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Rule not found or no changes applied"})
    return {"status": "ok"}


@router.delete("/postprocess-rules/{rule_id}")
async def delete_postprocess_rule(request: Request, rule_id: str):
    require_admin_write_access(request)
    db = _get_db()
    in_use = db.count(
        "SELECT COUNT(*) FROM tasks WHERE postprocess_rule_id = ? AND status IN ('pending', 'processing')",
        (rule_id,),
    )
    if in_use > 0:
        raise HTTPException(409, {"status": "error", "error": "RULE_IN_USE", "message": "Rule is used by active tasks"})
    caller_refs = db.count(
        "SELECT COUNT(*) FROM callers WHERE default_postprocess_rule_id = ?",
        (rule_id,),
    )
    if caller_refs > 0:
        raise HTTPException(409, {"status": "error", "error": "RULE_REFERENCED_BY_CALLERS", "message": "Rule is set as default postprocess rule by one or more callers"})
    deleted = db.delete_postprocess_rule(rule_id)
    if not deleted:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Rule not found"})
    return {"status": "ok"}


# Create the router
admin_router = router
