"""
Admin Authentication Module

Handles admin login, logout, password change, and session management.
Uses bcrypt for password hashing and signed cookies for session management.
"""

import os
import secrets
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.task_queue import TaskDatabase


# Default admin credentials
DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_PASSWORD_FROM_ENV = os.getenv("MINERU_ADMIN_INITIAL_PASSWORD")
_FALLBACK_ADMIN_PASSWORD = "admin123"

if _DEFAULT_PASSWORD_FROM_ENV:
    DEFAULT_ADMIN_PASSWORD = _DEFAULT_PASSWORD_FROM_ENV
else:
    DEFAULT_ADMIN_PASSWORD = _FALLBACK_ADMIN_PASSWORD
    logger.warning(
        "MINERU_ADMIN_INITIAL_PASSWORD not set - falling back to insecure default password 'admin123'. "
        "Set MINERU_ADMIN_INITIAL_PASSWORD in production."
    )

# Session cookie settings
SESSION_COOKIE_NAME = "admin_session"
SESSION_COOKIE_MAX_AGE = 3600 * 24  # 24 hours
SESSION_SECRET_MIN_LENGTH = 32

# Rate limiting
LOGIN_RATE_LIMIT_WINDOW = 60  # seconds
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
_login_attempts: dict = {}  # username -> [(timestamp, success), ...]


def _get_db() -> TaskDatabase:
    """Get database instance."""
    config = get_config()
    return TaskDatabase(db_path=config.db_path)


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt.
    
    Uses bcrypt with salt for secure password storage.
    bcrypt is a required dependency - deployment will fail if not installed.
    """
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.
    
    Args:
        password: Plain text password.
        password_hash: Stored password hash.
        
    Returns:
        True if password matches.
    """
    import bcrypt
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_hex(32)


def _generate_csrf_token() -> str:
    """Generate a CSRF token bound to an admin session."""
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    """Hash a session token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def init_default_admin() -> None:
    """Initialize default admin account if not exists."""
    db = _get_db()
    admin = db.get_admin(DEFAULT_ADMIN_USERNAME)
    
    if admin is None:
        password_hash = _hash_password(DEFAULT_ADMIN_PASSWORD)
        db.create_admin(DEFAULT_ADMIN_USERNAME, password_hash, must_change_password=True)
        # Log password setup info
        if _DEFAULT_PASSWORD_FROM_ENV:
            logger.info(f"Admin account created (username: {DEFAULT_ADMIN_USERNAME}) with password from MINERU_ADMIN_INITIAL_PASSWORD")
        else:
            logger.warning(
                "Admin account created with fallback default password 'admin123'. "
                "Set MINERU_ADMIN_INITIAL_PASSWORD env var to use a fixed password."
            )
    else:
        logger.info(f"Admin account already exists (username: {DEFAULT_ADMIN_USERNAME})")


def _cleanup_old_attempts(username: str) -> None:
    """Clean up old login attempts outside the rate limit window."""
    now = time.time()
    window_start = now - LOGIN_RATE_LIMIT_WINDOW
    
    if username not in _login_attempts:
        _login_attempts[username] = []
    
    # Clean old attempts
    _login_attempts[username] = [
        (ts, succ) for ts, succ in _login_attempts[username] if ts > window_start
    ]


def is_rate_limited(username: str) -> bool:
    """Check if user is currently rate limited (without recording).
    
    Args:
        username: Username to check.
        
    Returns:
        True if rate limited (too many failures), False otherwise.
    """
    _cleanup_old_attempts(username)
    
    # Count failures in current window
    failed_count = len([ts for ts, succ in _login_attempts[username] if not succ])
    return failed_count >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def record_login_failure(username: str) -> bool:
    """Record a login failure attempt.
    
    Args:
        username: Username that failed to login.
        
    Returns:
        True if allowed to continue, False if rate limited after this record.
    """
    _cleanup_old_attempts(username)
    
    now = time.time()
    # Record this failure
    _login_attempts[username].append((now, False))
    
    # Check if too many failures after recording
    failed_count = len([ts for ts, succ in _login_attempts[username] if not succ])
    if failed_count >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        logger.warning(f"Rate limit exceeded for user: {username}")
        return False
    
    return True


def clear_login_failures(username: str) -> None:
    """Clear all login failure attempts for a user (called on successful login).
    
    Args:
        username: Username to clear failures for.
    """
    if username in _login_attempts:
        _login_attempts[username] = []


def admin_login(username: str, password: str) -> dict:
    """Authenticate a user/admin account and create a shared session.
    
    Args:
        username: Admin username.
        password: Admin password.
        
    Returns:
        Dict with session_token, must_change_password, and user info.
        
    Raises:
        ValueError: If authentication fails or rate limited.
    """
    username = (username or "").strip()
    rate_limit_username = username.casefold()
    if is_rate_limited(rate_limit_username):
        raise ValueError("Too many login attempts. Please try again later.")
    
    db = _get_db()
    account = db.get_user_by_username(username)
    legacy_admin = None
    if account is None:
        legacy_admin = db.get_admin(username)

    if account is None and legacy_admin is None:
        logger.warning(f"Admin login attempt with unknown username: {username}")
        if not record_login_failure(rate_limit_username):
            raise ValueError("Too many login attempts. Please try again later.")
        raise ValueError("Invalid username or password")

    credentials = account or legacy_admin
    if (
        (account is not None and bool(account.get("disabled")))
        or not verify_password(password, credentials["password_hash"])
    ):
        logger.warning(f"Admin login attempt with incorrect password: {username}")
        if not record_login_failure(rate_limit_username):
            raise ValueError("Too many login attempts. Please try again later.")
        raise ValueError("Invalid username or password")

    role = account["role"] if account is not None else "admin"
    user_id = account["user_id"] if account is not None else None
    authenticated_username = credentials.get("username", username)

    # Create session
    session_token = _generate_session_token()
    token_hash = _hash_token(session_token)
    
    now = datetime.now()
    session_data = {
        "username": authenticated_username,
        "role": role,
        "user_id": user_id,
        "created_at": now.isoformat(timespec="microseconds"),
        "expires_at": (now + timedelta(seconds=SESSION_COOKIE_MAX_AGE)).isoformat(
            timespec="microseconds"
        ),
        "csrf_token": _generate_csrf_token(),
    }
    
    db.create_admin_session(token_hash, session_data)
    
    must_change_password = bool(credentials.get("must_change_password", 0) == 1)
    
    # Clear failed attempts on success
    clear_login_failures(rate_limit_username)
    
    logger.info(f"Account logged in: {authenticated_username} (role={role})")
    
    return {
        "session_token": session_token,
        "csrf_token": session_data["csrf_token"],
        "must_change_password": must_change_password,
        "username": authenticated_username,
        "display_name": account.get("display_name") if account else username,
        "role": role,
        "user_id": user_id,
    }


def admin_logout(session_token: str) -> bool:
    """Logout admin user and invalidate session.
    
    Args:
        session_token: Session token to invalidate.
        
    Returns:
        True if session was invalidated.
    """
    token_hash = _hash_token(session_token)
    db = _get_db()
    session_data = db.get_admin_session(token_hash)

    if session_data:
        db.delete_admin_session(token_hash)
        username = session_data.get("username")
        logger.info(f"Admin logged out: {username}")
        return True
    
    return False


def verify_session(session_token: str) -> Optional[dict]:
    """Verify session token and return session data if valid.
    
    Args:
        session_token: Session token to verify.
        
    Returns:
        Session data dict if valid, None if invalid/expired.
    """
    if not session_token:
        return None
    
    token_hash = _hash_token(session_token)
    db = _get_db()
    now = datetime.now()
    now_iso = now.isoformat(timespec="microseconds")
    db.delete_expired_admin_sessions(now_iso)
    session_data = db.get_admin_session(token_hash)
    
    if not session_data:
        return None
    
    # Check expiration
    expires_at = datetime.fromisoformat(session_data["expires_at"])
    if now > expires_at:
        db.delete_admin_session(token_hash)
        logger.debug(f"Admin session expired: {session_data.get('username')}")
        return None
    
    db.touch_admin_session(token_hash, now_iso)
    return session_data


def _validate_password_strength(password: str) -> bool:
    """Validate password meets minimum strength requirements.
    
    Args:
        password: Password to validate.
        
    Returns:
        True if password meets requirements.
        
    Raises:
        ValueError: If password is too weak.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    
    # Check for complexity (at least 2 of: uppercase, lowercase, digits, special chars)
    categories = 0
    if any(c.isupper() for c in password):
        categories += 1
    if any(c.islower() for c in password):
        categories += 1
    if any(c.isdigit() for c in password):
        categories += 1
    if any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password):
        categories += 1
    
    if categories < 2:
        raise ValueError("Password must contain at least 2 of: uppercase, lowercase, digits, special characters")
    
    return True


def admin_change_password(
    username: str,
    old_password: str,
    new_password: str,
    *,
    role: str = "admin",
    user_id: Optional[str] = None,
) -> dict:
    """Change the password for the authenticated account.
    
    Args:
        username: Admin username.
        old_password: Current password.
        new_password: New password.
        
    Returns:
        Dict with success status.
        
    Raises:
        ValueError: If password change fails or password is too weak.
    """
    # Validate new password strength
    _validate_password_strength(new_password)
    
    db = _get_db()
    new_password_hash = _hash_password(new_password)
    if user_id:
        user = db.get_user(user_id)
        if not user or user["username"] != username or user["role"] != role:
            raise ValueError("User not found")
        if not verify_password(old_password, user["password_hash"]):
            raise ValueError("Current password is incorrect")
        if not db.update_user(
            user_id,
            password_hash=new_password_hash,
            must_change_password=False,
        ):
            raise ValueError("User not found")
    else:
        admin = db.get_admin(username)
        if admin is None:
            raise ValueError("Admin not found")
        if not verify_password(old_password, admin["password_hash"]):
            raise ValueError("Current password is incorrect")
        db.update_admin_password(username, new_password_hash)

    logger.info(f"Account password changed: {username}")
    
    return {"success": True, "message": "Password changed successfully"}


def invalidate_all_sessions(username: str) -> int:
    """Invalidate all sessions for a specific admin (used after password change).
    
    Args:
        username: Admin username.
        
    Returns:
        Number of sessions invalidated.
    """
    invalidated = _get_db().delete_admin_sessions_for_username(username)

    if invalidated:
        logger.info(f"Invalidated {invalidated} sessions for {username}")

    return invalidated


@dataclass
class AdminUser:
    """Authenticated account info for the shared admin/portal session."""
    username: str
    must_change_password: bool
    role: str = "admin"
    user_id: Optional[str] = None
    caller_id: Optional[str] = None
    display_name: Optional[str] = None


def get_current_admin(session_token: str) -> Optional[AdminUser]:
    """Get current admin user from session token.
    
    Args:
        session_token: Session token.
        
    Returns:
        AdminUser if session valid, None otherwise.
    """
    from loguru import logger
    
    session_data = verify_session(session_token)
    if not session_data:
        logger.warning(f"get_current_admin: session invalid for token")
        return None
    
    db = _get_db()
    role = session_data.get("role", "admin")
    user_id = session_data.get("user_id")
    if user_id:
        user = db.get_user(user_id)
        if (
            not user
            or user.get("disabled")
            or user.get("role") != role
            or role not in {"user", "admin"}
        ):
            logger.warning(f"get_current_admin: user account unavailable for {session_data['username']}")
            return None
        caller = db.get_user_caller(user_id)
        return AdminUser(
            username=user["username"],
            must_change_password=bool(user.get("must_change_password", 0)),
            role=role,
            user_id=user_id,
            caller_id=caller.get("caller_id") if caller else None,
            display_name=user.get("display_name"),
        )

    if role != "admin":
        return None
    admin = db.get_admin(session_data["username"])
    if not admin:
        logger.warning(f"get_current_admin: admin not found for {session_data['username']}")
        return None
    return AdminUser(
        username=admin["username"],
        must_change_password=bool(admin.get("must_change_password", 0) == 1),
        role="admin",
        display_name=admin["username"],
    )


def get_default_admin_username() -> str:
    """Get the default admin username."""
    return DEFAULT_ADMIN_USERNAME


def get_default_admin_password() -> str:
    """Get the default admin password (for initial setup only).
    
    Note: This should only be used for initial setup or debugging.
    """
    return DEFAULT_ADMIN_PASSWORD
