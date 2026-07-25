"""
Admin API Module

REST API endpoints for admin console management.
Provides admin authentication, caller management, task viewing, and settings.
"""

import os
import base64
import secrets
import uuid
import re
import tempfile
import zipfile
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Response, File, UploadFile, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.postprocess import normalize_output_filename
from mineru_mcp.errors import from_exception
from mineru_mcp.task_queue import TaskDatabase
from mineru_mcp.task_queue.database import UNSET
from mineru_mcp.task_queue.file_manager import clean_display_name
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


class UpdateProfileRequest(BaseModel):
    locale: Optional[str] = None


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


class PostprocessActionCreateRequest(BaseModel):
    name: str
    prompt: str
    output_filename: str
    context_size: Optional[int] = None
    enabled: bool = True


class PostprocessActionUpdateRequest(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    output_filename: Optional[str] = None
    context_size: Optional[int] = None
    enabled: Optional[bool] = None


class PostprocessPlanStep(BaseModel):
    action_id: str
    output_filename: Optional[str] = None


class PostprocessPlanCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    steps: list[PostprocessPlanStep]
    enabled: bool = True


class PostprocessPlanUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[PostprocessPlanStep]] = None
    enabled: Optional[bool] = None


class PostprocessRunCreateRequest(BaseModel):
    plan_id: str


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
    
    db = _get_db()
    db_admin = db.get_admin(admin.username)
    locale = db_admin.get("locale", "") if db_admin else ""
    
    return {
        "username": admin.username,
        "must_change_password": admin.must_change_password,
        "locale": locale or None,
    }


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
            "locale": admin.get("locale"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(500, {"status": "error", "error": "INTERNAL_ERROR", "message": str(e)})


VALID_ADMIN_LOCALES = {"zh-CN", "en"}


@router.patch("/me")
async def update_current_user(request: Request, body: UpdateProfileRequest):
    """Update current admin user profile (e.g. locale preference)."""
    try:
        session = require_admin_session(request)
        require_same_origin(request)
        require_csrf_token(request, session)

        if body.locale is not None:
            locale = body.locale.strip()
            if locale not in VALID_ADMIN_LOCALES:
                raise HTTPException(
                    422,
                    {
                        "status": "error",
                        "error": "INVALID_LOCALE",
                        "message": f"Unsupported locale: {locale}. Supported: {', '.join(sorted(VALID_ADMIN_LOCALES))}",
                    },
                )
            db = _get_db()
            db.update_admin_locale(session["username"], locale)
            logger.info(f"Admin locale updated for {session['username']}: {locale}")

        return {"success": True, "message": "Profile updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile error: {e}")
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
async def create_caller(request: Request, response: Response, caller_req: CallerCreateRequest):
    """Create a new caller with API key."""
    require_admin_write_access(request)
    
    db = _get_db()
    if caller_req.default_postprocess_rule_id:
        plan = db.get_postprocess_plan(caller_req.default_postprocess_rule_id)
        if not plan or not int(plan.get("enabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_POSTPROCESS_PLAN", "message": "Default postprocess plan not found or disabled"})
    
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
    response.headers["Cache-Control"] = "no-store"
    
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
        plan = db.get_postprocess_plan(default_rule_id)
        if not plan or not int(plan.get("enabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_POSTPROCESS_PLAN", "message": "Default postprocess plan not found or disabled"})
    
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
async def reset_caller_key(request: Request, response: Response, caller_id: str):
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
    response.headers["Cache-Control"] = "no-store"
    
    return {
        "caller_id": caller_id,
        "api_key": api_key,  # Only returned once!
    }


@router.post("/callers/{caller_id}/reveal-key")
async def reveal_caller_key(request: Request, response: Response, caller_id: str):
    """Reveal a caller's current API key for explicit admin copy."""
    session = require_admin_write_access(request)

    db = _get_db()
    caller = db.get_caller(caller_id)
    if not caller:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Caller not found"})

    api_key = db.get_caller_api_key(caller_id)
    if api_key is None:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Caller not found"})

    logger.info(f"Admin revealed caller API key metadata: admin={session.get('username')} caller_id={caller_id}")
    response.headers["Cache-Control"] = "no-store"

    return {
        "caller_id": caller_id,
        "api_key": api_key,
        "disabled": bool(caller["disabled"]),
        "expires_at": caller["expires_at"],
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


def _derive_postprocess_status(db: TaskDatabase, task: dict) -> Optional[str]:
    """派生后处理展示状态：最新 run 的 status（running→processing 保持前端枚举兼容）。

    无 run 时回退 tasks 列原值（历史任务/未启用）。
    """
    latest = db.get_latest_postprocess_run(task["task_id"])
    if latest:
        status = latest["status"]
        return "processing" if status == "running" else status
    return task.get("postprocess_status")


def _admin_security_snapshot(db: TaskDatabase) -> dict:
    """返回管理端安全状态快照，不包含任何敏感明文。"""
    from mineru_mcp.admin_auth import verify_password

    admin_username = get_default_admin_username()
    admin = db.get_admin(admin_username)
    default_pw = get_default_admin_password()
    using_default_password = False
    if admin:
        using_default_password = verify_password(default_pw, admin["password_hash"])

    return {
        "default_password_in_use": using_default_password,
        "default_username": admin_username,
        "password_change_required": admin["must_change_password"] == 1 if admin else True,
    }


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_seconds(start: Optional[str], end: Optional[str]) -> Optional[float]:
    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end)
    if not start_dt or not end_dt:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds())


def _average(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def _classify_task_error(task: dict) -> dict:
    """粗粒度错误归因，面向管理台诊断展示。"""
    raw_error = (task.get("error") or task.get("message") or "").lower()
    if not raw_error:
        return {"category": "none", "suggestion": "当前任务没有错误信息"}
    if any(token in raw_error for token in ("validation", "invalid", "file", "upload", "pdf")):
        return {"category": "validation", "suggestion": "检查上传文件格式、大小和页码范围"}
    if any(token in raw_error for token in ("vlm", "api key", "base_url", "server", "model", "401", "403")):
        return {"category": "backend_config", "suggestion": "检查 backend、VLM server、api key 和 model 配置"}
    if any(token in raw_error for token in ("timeout", "timed out", "deadline")):
        return {"category": "timeout", "suggestion": "检查任务超时、VLM 响应时间或降低页码范围后重试"}
    if "postprocess" in raw_error or "llm" in raw_error:
        return {"category": "postprocess_error", "suggestion": "检查后处理 LLM 配置、prompt 和 context size"}
    if "mineru" in raw_error or "parse" in raw_error or "ocr" in raw_error:
        return {"category": "mineru_error", "suggestion": "尝试切换 backend 或使用 pipeline 复跑定位"}
    return {"category": "system_error", "suggestion": "查看任务日志和服务日志后再决定是否复跑"}


def _redact_url(value: str) -> str:
    return "<url>"


def _redact_diagnostic_text(value: Optional[str]) -> Optional[str]:
    """对管理台诊断文本做轻量脱敏，避免日志带出路径或密钥。"""
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"https?://[^\s'\"<>]+", lambda match: _redact_url(match.group(0)), text)
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2<redacted>",
        text,
    )
    text = re.sub(r"[A-Za-z]:\\[^\s]+", "<path>", text)
    text = re.sub(r"(?<![:\w/])/[^\s]+(?:/[^\s]+)+", "<path>", text)
    return text


def _safe_archive_name(artifact: dict, used_names: set[str]) -> str:
    """为 zip 内部路径生成稳定且安全的文件名。"""
    artifact_type = artifact.get("artifact_type") or "attachment"
    if artifact_type == "image_file":
        folder = "images"
    elif artifact_type in {"middle_json", "model_json", "content_list", "content_list_v2"} or "json" in artifact_type:
        folder = "json"
    elif "markdown" in artifact_type:
        folder = "markdown"
    else:
        folder = "attachments"

    raw_name = clean_display_name(artifact.get("filename") or artifact.get("name") or "artifact")
    candidate = f"{folder}/{raw_name}"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    stem = Path(raw_name).stem or "artifact"
    suffix = Path(raw_name).suffix
    index = 2
    while True:
        candidate = f"{folder}/{stem}-{index}{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


@router.get("/dashboard")
async def get_dashboard(request: Request):
    """Admin dashboard metrics.

    该接口只返回运营指标和脱敏任务摘要，不暴露 key、密文、摘要、绝对路径或堆栈。
    """
    require_admin_session(request)

    db = _get_db()
    now = datetime.now()
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    status_counts = {
        status: db.count("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,))
        for status in ("pending", "processing", "completed", "failed", "cancelled")
    }
    total_tasks = sum(status_counts.values())
    week_total = db.count("SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (week_ago,))
    week_completed = db.count(
        "SELECT COUNT(*) FROM tasks WHERE status = 'completed' AND created_at >= ?",
        (week_ago,),
    )
    week_failed = db.count(
        "SELECT COUNT(*) FROM tasks WHERE status = 'failed' AND created_at >= ?",
        (week_ago,),
    )
    day_total = db.count("SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (day_ago,))

    completed_rows = db.fetch_all(
        """
        SELECT created_at, started_at, completed_at
        FROM tasks
        WHERE status = 'completed' AND completed_at IS NOT NULL AND created_at >= ?
        ORDER BY completed_at DESC
        LIMIT 200
        """,
        (week_ago,),
    )
    queue_durations = [
        value
        for value in (_duration_seconds(row.get("created_at"), row.get("started_at")) for row in completed_rows)
        if value is not None
    ]
    parse_durations = [
        value
        for value in (_duration_seconds(row.get("started_at"), row.get("completed_at")) for row in completed_rows)
        if value is not None
    ]

    postprocess_counts = {
        status: db.count("SELECT COUNT(*) FROM postprocess_runs WHERE status = ?", (status,))
        for status in ("pending", "running", "completed", "failed", "cancelled")
    }

    caller_counts = {
        "total": db.count("SELECT COUNT(*) FROM callers"),
        "enabled": db.count(
            """
            SELECT COUNT(*) FROM callers
            WHERE disabled = 0 AND (expires_at IS NULL OR expires_at > ?)
            """,
            (now.isoformat(),),
        ),
        "disabled": db.count("SELECT COUNT(*) FROM callers WHERE disabled = 1"),
        "expired": db.count(
            "SELECT COUNT(*) FROM callers WHERE disabled = 0 AND expires_at IS NOT NULL AND expires_at <= ?",
            (now.isoformat(),),
        ),
    }

    recent_failed_rows = db.fetch_all(
        """
        SELECT t.task_id, t.input_filename, t.status, t.error, t.message,
               t.created_at, t.updated_at, t.completed_at, t.caller_id,
               c.name AS caller_name
        FROM tasks t
        LEFT JOIN callers c ON c.caller_id = t.caller_id
        WHERE t.status = 'failed'
        ORDER BY t.updated_at DESC
        LIMIT 5
        """
    )
    recent_failed = [
        {
            "task_id": row["task_id"],
            "input_filename": row["input_filename"],
            "status": row["status"],
            "message": row.get("error") or row.get("message") or "",
            "created_at": row["created_at"],
            "updated_at": row.get("updated_at"),
            "completed_at": row.get("completed_at"),
            "caller_id": row.get("caller_id"),
            "caller_name": row.get("caller_name"),
        }
        for row in recent_failed_rows
    ]

    config = get_config()
    return {
        "generated_at": now.isoformat(),
        "queue": {
            **status_counts,
            "total": total_tasks,
        },
        "recent": {
            "last_24h_total": day_total,
            "last_7d_total": week_total,
            "last_7d_completed": week_completed,
            "last_7d_failed": week_failed,
            "last_7d_success_rate": round(week_completed / week_total * 100, 1) if week_total else None,
            "last_7d_failure_rate": round(week_failed / week_total * 100, 1) if week_total else None,
        },
        "durations": {
            "avg_queue_seconds": _average(queue_durations),
            "avg_parse_seconds": _average(parse_durations),
        },
        "postprocess": postprocess_counts,
        "callers": caller_counts,
        "runtime": {
            "default_backend": config.default_backend,
            "max_concurrent": config.max_concurrent,
            "postprocess_max_concurrent": config.postprocess_max_concurrent,
        },
        "admin_security": _admin_security_snapshot(db),
        "recent_failed_tasks": recent_failed,
    }


@router.get("/diagnostics")
async def get_diagnostics(request: Request):
    """Admin configuration diagnostics.

    返回结构化检查结果，只描述配置状态，不返回密钥值。
    """
    require_admin_session(request)

    config = get_config()
    db = _get_db()
    checks = []

    def add_check(key: str, status: str, severity: str, message: str, action_hint: str = ""):
        checks.append({
            "key": key,
            "status": status,
            "severity": severity,
            "message": message,
            "action_hint": action_hint,
        })

    from mineru_mcp.config import VALID_BACKENDS
    if config.default_backend in VALID_BACKENDS:
        add_check("default_backend", "ok", "info", f"默认 backend: {config.default_backend}")
    else:
        add_check("default_backend", "failed", "critical", "默认 backend 不在白名单中", "检查 MINERU_DEFAULT_BACKEND")

    needs_vlm = config.default_backend.endswith("-http-client")
    vlm_ready = bool(config.vlm_base_url and config.vlm_api_key and config.vlm_model)
    if needs_vlm and not vlm_ready:
        add_check(
            "vlm_config",
            "failed",
            "critical",
            "默认 backend 需要远程 VLM，但 VLM server、api key 或 model 未完整配置",
            "设置 MINERU_VL_SERVER、MINERU_VL_API_KEY、MINERU_VL_MODEL_NAME，或改用 pipeline",
        )
    elif needs_vlm:
        add_check("vlm_config", "ok", "info", "远程 VLM 配置已提供")
    else:
        add_check("vlm_config", "skipped", "info", "当前默认 backend 不要求远程 VLM")

    postprocess_ready = bool(config.title_base_url and config.title_api_key and config.title_model)
    if postprocess_ready:
        add_check("postprocess_llm", "ok", "info", "后处理 LLM 配置已提供")
    else:
        add_check(
            "postprocess_llm",
            "warning",
            "warning",
            "后处理 LLM 未完整配置，手动或自动后处理将不可用",
            "设置 MINERU_TITLE_BASE_URL、MINERU_TITLE_API_KEY、MINERU_TITLE_MODEL",
        )

    output_root = Path(config.output_root)
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / ".mineru_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        add_check("output_root", "ok", "info", "输出目录可写")
    except Exception:
        add_check("output_root", "failed", "critical", "输出目录不可写", "检查 MINERU_OUTPUT_ROOT 权限")

    db_parent = Path(config.db_path).parent
    try:
        db_parent.mkdir(parents=True, exist_ok=True)
        probe = db_parent / ".mineru_db_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        add_check("db_path", "ok", "info", "数据库目录可写")
    except Exception:
        add_check("db_path", "failed", "critical", "数据库目录不可写", "检查 MINERU_DB_PATH 权限")

    from mineru_mcp.caller_key_crypto import validate_master_key
    try:
        validate_master_key(config.caller_key_master_key or "")
        add_check("caller_key_master_key", "ok", "info", "caller key 主密钥有效")
    except ValueError:
        add_check(
            "caller_key_master_key",
            "failed",
            "critical",
            "caller key 主密钥缺失或格式无效",
            "设置有效的 MINERU_CALLER_KEY_MASTER_KEY",
        )

    admin_security = _admin_security_snapshot(db)
    if admin_security["default_password_in_use"] or admin_security["password_change_required"]:
        add_check(
            "admin_password",
            "warning",
            "warning",
            "管理员密码仍处于默认或必须修改状态",
            "进入系统设置修改管理员密码",
        )
    else:
        add_check("admin_password", "ok", "info", "管理员密码已修改")

    add_check(
        "single_instance",
        "warning",
        "warning",
        "当前 SQLite 队列和进程内调度器按单实例部署设计",
        "如需多副本部署，请先设计共享 session、队列租约和调度协调",
    )

    priority = {"failed": 3, "warning": 2, "skipped": 1, "ok": 0}
    overall = "healthy"
    if any(check["status"] == "failed" for check in checks):
        overall = "critical"
    elif any(check["status"] == "warning" for check in checks):
        overall = "warning"

    return {
        "status": overall,
        "generated_at": datetime.now().isoformat(),
        "checks": sorted(checks, key=lambda item: priority.get(item["status"], 0), reverse=True),
    }

@router.get("/tasks")
async def list_tasks(
    request: Request,
    caller_id: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    key: str = "",
    task_id: str = "",
    filename: str = "",
    backend: str = "",
    postprocess_status: str = "",
    stale_processing_minutes: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    """List tasks with filters."""
    require_admin_session(request)
    
    db = _get_db()
    
    # Build query
    conditions = []
    params = []
    
    if caller_id == "__unassigned__":
        conditions.append("caller_id IS NULL")
    elif caller_id:
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

    if filename:
        conditions.append("input_filename LIKE ?")
        params.append(f"%{filename}%")

    if backend:
        conditions.append("backend = ?")
        params.append(backend)

    if postprocess_status:
        conditions.append(
            """
            COALESCE(
                (
                    SELECT CASE WHEN ppr.status = 'running' THEN 'processing' ELSE ppr.status END
                    FROM postprocess_runs ppr
                    WHERE ppr.task_id = tasks.task_id
                    ORDER BY ppr.created_at DESC
                    LIMIT 1
                ),
                postprocess_status
            ) = ?
            """
        )
        params.append(postprocess_status)

    if stale_processing_minutes > 0:
        cutoff = (datetime.now() - timedelta(minutes=stale_processing_minutes)).isoformat()
        conditions.append("status = 'processing' AND started_at IS NOT NULL AND started_at <= ?")
        params.append(cutoff)
    
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
            "postprocess_status": _derive_postprocess_status(db, task),
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
    caller_id: Optional[str] = Form(default=None),
):
    """Create a new task from admin console.

    caller_id 可选：指派后任务归属该调用方（owner=caller），其 API key 即可通过
    公开 API/MCP 查询与下载该任务；不指派则仅管理台可见（owner=admin-console）。
    """
    require_admin_write_access(request)
    try:
        db = _get_db()
        if caller_id:
            caller = db.get_caller(caller_id)
            if not caller:
                raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller not found"})
            if int(caller.get("disabled", 0)):
                raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller is disabled"})
            principal = CurrentPrincipal(
                principal_id=caller_id,
                principal_type=PrincipalType.API_KEY,
                role=PrincipalRole.USER,
                display_name=caller.get("name") or caller_id,
                caller_id=caller_id,
            )
        else:
            principal = CurrentPrincipal(
                principal_id="admin-console",
                principal_type=PrincipalType.SINGLE_USER,
                role=PrincipalRole.ADMIN,
                display_name="Admin Console",
            )

        # Read file bytes
        file_bytes = await file.read()
        validate_upload_file(file.filename, file_bytes)  # validation only
        file_b64 = base64.b64encode(file_bytes).decode()

        from mineru_mcp.services import get_task_service
        task_service = get_task_service()

        result = task_service.create_task_from_base64(
            file_base64=file_b64,
            file_name=file.filename,
            backend=backend if backend else None,
            lang=lang,
            enable_postprocess=enable_postprocess,
            postprocess_rule_id=postprocess_rule_id,
            postprocess_context_size=postprocess_context_size,
            principal=principal,
        )

        return {
            "status": "ok",
            "task_id": result["task_id"],
            "message": "Task created",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin create task error: {e}")
        err = from_exception(e)
        raise HTTPException(err.http_status, err.to_dict())


class TaskCallerUpdateRequest(BaseModel):
    caller_id: Optional[str] = None  # null/空串 = 取消指派（回归 admin-console 归属）


class TaskCloneRequest(BaseModel):
    backend: Optional[str] = None
    lang: Optional[str] = None
    formula_enable: Optional[bool] = None
    table_enable: Optional[bool] = None
    image_analysis: Optional[bool] = None
    server_url: Optional[str] = None
    start_page_id: Optional[int] = None
    end_page_id: Optional[int] = None
    enable_postprocess: Optional[bool] = None
    postprocess_rule_id: Optional[str] = None
    postprocess_context_size: Optional[int] = None
    caller_id: Optional[str] = None
    inherit_caller: bool = True


@router.patch("/tasks/{task_id}/caller")
async def update_task_caller(request: Request, task_id: str, payload: TaskCallerUpdateRequest):
    """修改任务归属调用方。

    指派：owner_id/owner_type/caller_id 同步写到该 caller 名下，其 API key
    即可经公开 API/MCP 访问该任务；取消指派：回归 admin-console 归属（仅管理台可见）。
    """
    require_admin_write_access(request)
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    caller_id = (payload.caller_id or "").strip()
    if caller_id:
        caller = db.get_caller(caller_id)
        if not caller:
            raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller not found"})
        if int(caller.get("disabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller is disabled"})
        db.execute(
            "UPDATE tasks SET caller_id = ?, owner_id = ?, owner_type = 'api_key', updated_at = ? WHERE task_id = ?",
            (caller_id, caller_id, datetime.now().isoformat(), task_id),
        )
        logger.info(f"Task {task_id} reassigned to caller {caller_id}")
    else:
        db.execute(
            "UPDATE tasks SET caller_id = NULL, owner_id = 'admin-console', owner_type = 'single_user', updated_at = ? WHERE task_id = ?",
            (datetime.now().isoformat(), task_id),
        )
        logger.info(f"Task {task_id} caller assignment cleared")
    return {"status": "ok"}


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


@router.post("/tasks/{task_id}/reprocess")
async def reprocess_task(request: Request, task_id: str):
    """重新处理失败的任务：清除残留产物，重置为 pending 重新调度。

    仅允许 failed 状态的任务重处理。
    """
    require_admin_write_access(request)

    import shutil

    from mineru_mcp.task_queue import FileManager
    from mineru_mcp.task_queue.file_manager import resolve_stored_filename

    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    if task["status"] != "failed":
        raise HTTPException(
            409,
            {"status": "error", "error": "TASK_NOT_FAILED", "message": f"仅失败任务可重处理，当前状态: {task['status']}"},
        )

    task_dir_obj = Path(task["task_dir"])
    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir_obj)
    source_file = task_dir_obj / stored_name

    if not source_file.exists():
        raise HTTPException(
            404,
            {"status": "error", "error": "SOURCE_NOT_FOUND", "message": "原始文件已不存在，无法重处理"},
        )

    # 清理上一次失败的残留产物（MinerU 输出子目录），避免脏数据干扰校验
    fm = FileManager(output_root=get_config().output_root)
    output_subdir = fm.get_output_dir(task_dir_obj, stored_name, task.get("backend", "vlm-auto-engine"))
    if output_subdir.exists():
        shutil.rmtree(output_subdir, ignore_errors=True)
        logger.info(f"Task {task_id}: cleaned stale output {output_subdir}")

    # 重置任务状态为 pending，调度器会自动拾取
    now = datetime.now().isoformat()
    updated = db.execute(
        "UPDATE tasks SET status = 'pending', progress = 0, error = NULL,"
        " message = 'Queued for reprocessing', started_at = NULL,"
        " completed_at = NULL, retry_count = retry_count + 1, updated_at = ?"
        " WHERE task_id = ? AND status = 'failed'",
        (now, task_id),
    )

    if not updated:
        raise HTTPException(
            409,
            {"status": "error", "error": "CONCURRENT_MODIFICATION", "message": "任务状态已被其他操作修改"},
        )

    logger.info(f"Task {task_id} requeued for reprocessing (retry_count={task.get('retry_count', 0) + 1})")
    return {"status": "ok", "message": "任务已重新加入队列"}


@router.post("/tasks/{task_id}/clone")
async def clone_task(request: Request, task_id: str, payload: TaskCloneRequest):
    """复制任务为一个新任务。

    复制会把原始上传文件写入新任务目录；旧任务产物、错误日志和后处理执行记录不会复制。
    payload 中显式传入的字段会覆盖原任务参数，未传入则继承原任务参数。
    """
    require_admin_write_access(request)

    from mineru_mcp.services import get_task_service
    from mineru_mcp.task_queue.file_manager import resolve_stored_filename

    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    task_dir_obj = Path(task["task_dir"])
    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir_obj)
    source_file = task_dir_obj / stored_name
    if not source_file.exists():
        raise HTTPException(
            404,
            {"status": "error", "error": "SOURCE_NOT_FOUND", "message": "原始文件已不存在，无法复制任务"},
        )

    if "caller_id" in payload.model_fields_set:
        effective_caller_id = (payload.caller_id or "").strip() or None
    elif payload.inherit_caller:
        effective_caller_id = task.get("caller_id")
    else:
        effective_caller_id = None

    if effective_caller_id:
        caller = db.get_caller(effective_caller_id)
        if not caller:
            raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller not found"})
        if int(caller.get("disabled", 0)):
            raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller is disabled"})
        expires_at = caller.get("expires_at")
        if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
            raise HTTPException(400, {"status": "error", "error": "INVALID_CALLER", "message": "Caller is expired"})
        principal = CurrentPrincipal(
            principal_id=effective_caller_id,
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
            display_name=caller.get("name") or effective_caller_id,
            caller_id=effective_caller_id,
        )
    else:
        principal = CurrentPrincipal(
            principal_id="admin-console",
            principal_type=PrincipalType.SINGLE_USER,
            role=PrincipalRole.ADMIN,
            display_name="Admin Console",
        )

    def pick(name: str, default):
        return getattr(payload, name) if name in payload.model_fields_set else default

    try:
        result = get_task_service().create_task_from_file(
            source_path=source_file,
            file_name=task["input_filename"],
            backend=pick("backend", task.get("backend")),
            lang=pick("lang", task.get("lang") or "ch"),
            formula_enable=pick("formula_enable", bool(task.get("formula_enable", 1))),
            table_enable=pick("table_enable", bool(task.get("table_enable", 1))),
            image_analysis=pick("image_analysis", bool(task.get("image_analysis", 1))),
            server_url=pick("server_url", task.get("server_url")),
            start_page_id=pick("start_page_id", task.get("start_page_id", 0)),
            end_page_id=pick("end_page_id", task.get("end_page_id", 99999)),
            enable_postprocess=pick("enable_postprocess", bool(task.get("enable_postprocess", 0))),
            postprocess_rule_id=pick("postprocess_rule_id", task.get("postprocess_rule_id")),
            postprocess_context_size=pick("postprocess_context_size", task.get("postprocess_context_size")),
            principal=principal,
        )
        db.add_log(result["task_id"], "INFO", f"Cloned from task {task_id}")
        logger.info(f"Task {task_id} cloned to {result['task_id']}")
        return {
            "status": "ok",
            "source_task_id": task_id,
            "task_id": result["task_id"],
            "message": "Task cloned",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin clone task error: {e}")
        err = from_exception(e)
        raise HTTPException(err.http_status, err.to_dict())


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
            from mineru_mcp.task_queue.file_manager import resolve_stored_filename

            file_manager = FileManager(output_root=get_config().output_root)
            task_dir_obj = Path(task["task_dir"])
            stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir_obj)
            output_files = file_manager.get_output_files(
                task_dir_obj,
                stored_name,
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
        "postprocess_status": _derive_postprocess_status(db, task),
    }


@router.get("/tasks/{task_id}/diagnostics")
async def get_task_diagnostics(request: Request, task_id: str):
    """返回单个任务的管理端诊断信息。

    诊断信息用于解释任务参数、耗时、错误归因和最近日志，不返回
    server_url 明文、key、output 绝对路径或异常堆栈。
    """
    require_admin_session(request)

    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    latest_run = db.get_latest_postprocess_run(task_id)
    postprocess_status = _derive_postprocess_status(db, task)
    queue_seconds = _duration_seconds(task.get("created_at"), task.get("started_at"))
    parse_seconds = _duration_seconds(task.get("started_at"), task.get("completed_at"))
    total_seconds = _duration_seconds(task.get("created_at"), task.get("completed_at"))
    postprocess_seconds = None
    if latest_run:
        postprocess_seconds = _duration_seconds(latest_run.get("started_at"), latest_run.get("finished_at"))

    output_validation = None
    if task.get("status") == "completed":
        try:
            from mineru_mcp.task_queue import FileManager
            from mineru_mcp.task_queue.file_manager import resolve_stored_filename

            fm = FileManager(output_root=get_config().output_root)
            task_dir = Path(task["task_dir"])
            stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir)
            output_validation = fm.validate_task_outputs(task_dir, stored_name, task.get("backend", "vlm-auto-engine"))
        except Exception as exc:
            logger.warning(f"Task {task_id}: failed to validate outputs for diagnostics: {exc}")
            output_validation = {
                "required_missing": [],
                "recommended_missing": [],
                "optional_missing": [],
                "diagnostic_error": "OUTPUT_VALIDATION_FAILED",
            }

    logs = db.get_logs(task_id)[-20:]
    safe_logs = [
        {
            "level": item.get("level"),
            "message": _redact_diagnostic_text(item.get("message")),
            "created_at": item.get("created_at"),
        }
        for item in logs
    ]

    return {
        "task_id": task_id,
        "status": task.get("status"),
        "postprocess_status": postprocess_status,
        "request": {
            "backend": task.get("backend"),
            "lang": task.get("lang"),
            "formula_enable": bool(task.get("formula_enable", 0)),
            "table_enable": bool(task.get("table_enable", 0)),
            "image_analysis": bool(task.get("image_analysis", 0)),
            "start_page_id": task.get("start_page_id"),
            "end_page_id": task.get("end_page_id"),
            "server_url_configured": bool(task.get("server_url")),
            "enable_postprocess": bool(task.get("enable_postprocess", 0)),
            "postprocess_rule_id": task.get("postprocess_rule_id"),
            "postprocess_context_size": task.get("postprocess_context_size"),
        },
        "timeline": {
            "created_at": task.get("created_at"),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "postprocess_started_at": latest_run.get("started_at") if latest_run else None,
            "postprocess_finished_at": latest_run.get("finished_at") if latest_run else None,
        },
        "durations": {
            "queue_seconds": queue_seconds,
            "parse_seconds": parse_seconds,
            "postprocess_seconds": postprocess_seconds,
            "total_seconds": total_seconds,
        },
        "error": _classify_task_error(task),
        "output_validation": output_validation,
        "logs": safe_logs,
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

    # 解析完成即任务完成（后处理 run 独立生命周期，不再与主状态共享阶段）
    parse_stage_done = status == TaskStatus.COMPLETED

    if not parse_stage_done:
        return {
            "task_id": task_id,
            "status": status.value,
            "artifacts": [],
        }

    # Use TaskService.list_deliverables() to get unified artifact structure
    result = task_service.list_deliverables(task_id)
    artifact_items = result.get("artifacts", [])
    
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


@router.get("/tasks/{task_id}/deliverables/archive")
async def download_task_deliverables_archive(request: Request, task_id: str):
    """Download all exposed deliverables for a completed task as a zip archive."""
    require_admin_session(request)

    from mineru_mcp.task_queue import FileManager
    from mineru_mcp.task_queue.file_manager import resolve_stored_filename
    from mineru_mcp.services.task_service import collect_postprocess_filenames

    config = get_config()
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    if task["status"] != "completed":
        raise HTTPException(409, {"status": "error", "error": "TASK_NOT_COMPLETED", "message": "Task is not completed"})

    fm = FileManager(output_root=config.output_root)
    task_dir = Path(task["task_dir"])
    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir)
    postprocess_filenames = collect_postprocess_filenames(db, task)
    allowed_keys = fm.get_allowed_download_keys(
        task_dir,
        stored_name,
        task["backend"],
        postprocess_filenames,
    )
    artifacts = fm.list_task_artifacts(
        task_dir,
        stored_name,
        task["backend"],
        postprocess_filenames,
        display_name=task["input_filename"],
    )

    zip_file = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
    used_names: set[str] = set()
    with zipfile.ZipFile(zip_file, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifacts:
            download_key = artifact.get("download_key")
            if not artifact.get("downloadable") or not isinstance(download_key, str) or download_key not in allowed_keys:
                continue
            try:
                file_path = fm.resolve_download_key(task_dir, download_key)
            except ValueError:
                continue
            if not file_path.exists() or not file_path.is_file():
                continue
            archive.write(file_path, _safe_archive_name(artifact, used_names))

    zip_file.seek(0)

    def iter_archive():
        try:
            while True:
                chunk = zip_file.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            zip_file.close()

    archive_name = f"{Path(task['input_filename']).stem or task_id}-deliverables.zip"
    return StreamingResponse(
        iter_archive(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{clean_display_name(archive_name)}"',
            "Cache-Control": "no-store",
        },
    )


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

    # 解析完成即任务完成；后处理 run 不再与主状态共享 processing 阶段
    parse_stage_done = task["status"] == "completed"
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
    from mineru_mcp.task_queue.file_manager import resolve_stored_filename
    from mineru_mcp.services.task_service import collect_postprocess_filenames
    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir)
    allowed_keys = file_manager.get_allowed_download_keys(
        task_dir,
        stored_name,
        task["backend"],
        collect_postprocess_filenames(db, task),
    )
    if download_key not in allowed_keys:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "File not found"})
    
    # 3. Verify the file actually exists
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "File not found"})
    
    media_type = file_manager.get_media_type_for_path(file_path)
    disposition = "inline" if inline else "attachment"
    # Map primary markdown download name back to original display stem
    output_files = file_manager.get_output_files(task_dir, stored_name, task["backend"])
    download_filename = file_path.name
    if file_path == output_files["md"]:
        download_filename = f"{Path(task['input_filename']).stem}.md"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=download_filename,
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
    from mineru_mcp.task_queue.file_manager import resolve_stored_filename
    stored_name = resolve_stored_filename(task["task_id"], task["input_filename"], task_dir)
    source_path = task_dir / stored_name
    
    if not source_path.exists():
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Source file not found"})
    
    download_name = name if name else task["input_filename"]
    
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
    
    return {
        "max_concurrent": config.max_concurrent,
        "max_concurrent_source": "MINERU_MAX_CONCURRENT env var",
        "max_concurrent_note": "Modifying this value requires service restart",
        "admin_security": _admin_security_snapshot(db),
    }


# ========== Postprocess Actions / Plans / Runs ==========


def _get_postprocess_runner(db: TaskDatabase):
    """取进程内 runner；未装配时退回临时实例（TestClient 等场景）。"""
    from mineru_mcp.app import get_postprocess_runner
    runner = get_postprocess_runner()
    if runner is not None:
        return runner
    from mineru_mcp.task_queue import PostprocessRunner
    return PostprocessRunner(db=db, config=get_config())


def _plans_referencing_action(db: TaskDatabase, action_id: str, enabled_only: bool = False) -> list:
    refs = []
    for plan in db.list_postprocess_plans(include_disabled=not enabled_only):
        if any(step.get("action_id") == action_id for step in plan.get("steps") or []):
            refs.append(plan)
    return refs


@router.get("/postprocess-actions")
async def list_postprocess_actions(request: Request, include_disabled: bool = True):
    require_admin_session(request)
    db = _get_db()
    return {"items": db.list_postprocess_actions(include_disabled=include_disabled)}


@router.post("/postprocess-actions")
async def create_postprocess_action(request: Request, payload: PostprocessActionCreateRequest):
    require_admin_write_access(request)
    db = _get_db()
    name = payload.name.strip()
    prompt = payload.prompt.strip()
    if not name:
        raise HTTPException(400, {"status": "error", "error": "INVALID_NAME", "message": "Name is required"})
    if not prompt:
        raise HTTPException(400, {"status": "error", "error": "INVALID_PROMPT", "message": "Prompt is required"})
    try:
        output_filename = normalize_output_filename(payload.output_filename)
    except ValueError as exc:
        raise HTTPException(400, {"status": "error", "error": "INVALID_OUTPUT_FILENAME", "message": str(exc)})

    action_id = f"ppa-{uuid.uuid4().hex[:12]}"
    db.create_postprocess_action(
        action_id=action_id,
        name=name,
        config={"prompt": prompt, "output_filename": output_filename, "context_size": payload.context_size},
        enabled=payload.enabled,
    )
    return {"status": "ok", "action_id": action_id}


@router.put("/postprocess-actions/{action_id}")
async def update_postprocess_action(request: Request, action_id: str, payload: PostprocessActionUpdateRequest):
    require_admin_write_access(request)
    db = _get_db()
    action = db.get_postprocess_action(action_id)
    if not action:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Action not found"})

    if payload.enabled is False:
        refs = _plans_referencing_action(db, action_id, enabled_only=True)
        if refs:
            raise HTTPException(409, {"status": "error", "error": "ACTION_REFERENCED_BY_PLANS", "message": "Action is used by one or more enabled plans"})

    new_config = dict(action.get("config") or {})
    if payload.prompt is not None:
        prompt = payload.prompt.strip()
        if not prompt:
            raise HTTPException(400, {"status": "error", "error": "INVALID_PROMPT", "message": "Prompt is required"})
        new_config["prompt"] = prompt
    if payload.output_filename is not None:
        try:
            new_config["output_filename"] = normalize_output_filename(payload.output_filename)
        except ValueError as exc:
            raise HTTPException(400, {"status": "error", "error": "INVALID_OUTPUT_FILENAME", "message": str(exc)})
    if payload.context_size is not None:
        new_config["context_size"] = payload.context_size

    db.update_postprocess_action(
        action_id,
        name=payload.name.strip() if payload.name is not None else None,
        config=new_config,
        enabled=payload.enabled,
    )
    return {"status": "ok"}


@router.delete("/postprocess-actions/{action_id}")
async def delete_postprocess_action(request: Request, action_id: str):
    require_admin_write_access(request)
    db = _get_db()
    refs = _plans_referencing_action(db, action_id)
    if refs:
        raise HTTPException(409, {"status": "error", "error": "ACTION_REFERENCED_BY_PLANS", "message": "Action is used by one or more plans"})
    deleted = db.delete_postprocess_action(action_id)
    if not deleted:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Action not found"})
    return {"status": "ok"}


@router.get("/postprocess-plans")
async def list_postprocess_plans(request: Request, include_disabled: bool = True):
    require_admin_session(request)
    db = _get_db()
    return {
        "items": db.list_postprocess_plans(include_disabled=include_disabled),
        "default_context_size": get_config().postprocess_context_size,
    }


def _validate_plan_steps_payload(db: TaskDatabase, steps: list[PostprocessPlanStep]):
    """保存前校验：步骤可解析（action 存在/启用/类型支持、文件名合法）。"""
    from mineru_mcp.task_queue.postprocess_runner import resolve_steps_snapshot
    try:
        resolve_steps_snapshot(db, [step.model_dump() for step in steps], plan_label="Plan")
    except ValueError as exc:
        raise HTTPException(400, {"status": "error", "error": "INVALID_PLAN_STEPS", "message": str(exc)})


@router.post("/postprocess-plans")
async def create_postprocess_plan(request: Request, payload: PostprocessPlanCreateRequest):
    require_admin_write_access(request)
    db = _get_db()
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, {"status": "error", "error": "INVALID_TITLE", "message": "Title is required"})
    if not payload.steps:
        raise HTTPException(400, {"status": "error", "error": "INVALID_PLAN_STEPS", "message": "Plan requires at least one step"})
    _validate_plan_steps_payload(db, payload.steps)

    plan_id = f"ppp-{uuid.uuid4().hex[:12]}"
    db.create_postprocess_plan(
        plan_id=plan_id,
        title=title,
        description=payload.description,
        steps=[step.model_dump() for step in payload.steps],
        enabled=payload.enabled,
    )
    return {"status": "ok", "plan_id": plan_id}


@router.put("/postprocess-plans/{plan_id}")
async def update_postprocess_plan(request: Request, plan_id: str, payload: PostprocessPlanUpdateRequest):
    require_admin_write_access(request)
    db = _get_db()
    plan = db.get_postprocess_plan(plan_id)
    if not plan:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Plan not found"})

    if payload.enabled is False:
        caller_refs = db.count(
            "SELECT COUNT(*) FROM callers WHERE default_postprocess_rule_id = ?",
            (plan_id,),
        )
        if caller_refs > 0:
            raise HTTPException(409, {"status": "error", "error": "PLAN_REFERENCED_BY_CALLERS", "message": "Plan is set as default postprocess plan by one or more callers"})

    steps_payload = None
    if payload.steps is not None:
        if not payload.steps:
            raise HTTPException(400, {"status": "error", "error": "INVALID_PLAN_STEPS", "message": "Plan requires at least one step"})
        _validate_plan_steps_payload(db, payload.steps)
        steps_payload = [step.model_dump() for step in payload.steps]

    db.update_postprocess_plan(
        plan_id,
        title=payload.title.strip() if payload.title is not None else None,
        description=payload.description,
        steps=steps_payload,
        enabled=payload.enabled,
    )
    return {"status": "ok"}


@router.delete("/postprocess-plans/{plan_id}")
async def delete_postprocess_plan(request: Request, plan_id: str):
    require_admin_write_access(request)
    db = _get_db()
    in_use = db.count(
        "SELECT COUNT(*) FROM tasks WHERE postprocess_rule_id = ? AND status IN ('pending', 'processing')",
        (plan_id,),
    )
    if in_use > 0:
        raise HTTPException(409, {"status": "error", "error": "PLAN_IN_USE", "message": "Plan is used by active tasks"})
    caller_refs = db.count(
        "SELECT COUNT(*) FROM callers WHERE default_postprocess_rule_id = ?",
        (plan_id,),
    )
    if caller_refs > 0:
        raise HTTPException(409, {"status": "error", "error": "PLAN_REFERENCED_BY_CALLERS", "message": "Plan is set as default postprocess plan by one or more callers"})
    deleted = db.delete_postprocess_plan(plan_id)
    if not deleted:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Plan not found"})
    return {"status": "ok"}


# ========== Postprocess Runs（Admin 手动触发/查询/取消） ==========


@router.post("/tasks/{task_id}/postprocess-runs")
async def create_task_postprocess_run(request: Request, task_id: str, payload: PostprocessRunCreateRequest):
    """对已完成任务手动触发一个后处理 run。"""
    require_admin_write_access(request)
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})
    if task["status"] != "completed":
        raise HTTPException(409, {"status": "error", "error": "TASK_NOT_COMPLETED", "message": f"Task status is '{task['status']}', postprocess requires 'completed'"})

    from mineru_mcp.postprocess import TitleLLMPostprocessor
    postprocessor = TitleLLMPostprocessor(get_config())
    if not postprocessor.is_configured():
        raise HTTPException(400, {"status": "error", "error": "POSTPROCESS_LLM_NOT_CONFIGURED", "message": postprocessor.get_config_error_message()})

    try:
        run_id = _get_postprocess_runner(db).create_run(task_id, payload.plan_id, trigger_source="manual")
    except ValueError as exc:
        raise HTTPException(400, {"status": "error", "error": "INVALID_POSTPROCESS_PLAN", "message": str(exc)})
    return {"status": "ok", "run_id": run_id}


@router.get("/tasks/{task_id}/postprocess-runs")
async def list_task_postprocess_runs(request: Request, task_id: str):
    """任务的后处理 run 列表（含步骤状态）。"""
    require_admin_session(request)
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Task not found"})

    from mineru_mcp.services.task_service import serialize_postprocess_run
    runs = db.list_postprocess_runs(task_id=task_id)
    runs = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    return {"items": [serialize_postprocess_run(run) for run in runs]}


@router.post("/postprocess-runs/{run_id}/cancel")
async def cancel_postprocess_run(request: Request, run_id: str):
    """取消后处理 run：pending 直接取消；running 在分片边界生效。"""
    require_admin_write_access(request)
    db = _get_db()
    run = db.get_postprocess_run(run_id)
    if not run:
        raise HTTPException(404, {"status": "error", "error": "NOT_FOUND", "message": "Run not found"})
    cancelled = _get_postprocess_runner(db).cancel_run(run_id)
    if not cancelled:
        raise HTTPException(409, {"status": "error", "error": "RUN_NOT_CANCELLABLE", "message": f"Run status is '{run['status']}'"})
    return {"status": "ok"}


# Create the router
admin_router = router
