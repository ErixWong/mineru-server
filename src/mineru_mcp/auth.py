"""
Authentication Module

Provides Bearer Token authentication for HTTP REST/MCP requests.
The only supported external authentication path is caller API keys stored in
`callers` table. Admin console uses its own session-cookie model separately.
"""

import secrets
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from loguru import logger

from mineru_mcp.errors import auth_missing, auth_invalid, MCPError
from mineru_mcp.principal import (
    CurrentPrincipal,
    PrincipalType,
    PrincipalRole,
    DEFAULT_SINGLE_USER_PRINCIPAL,
)


class AuthMode(str, Enum):
    """Authentication modes supported by the server."""
    DATABASE_API_KEY = "database_api_key"
    NONE = "none"


_detected_auth_mode: Optional[AuthMode] = None


def _detect_auth_mode() -> AuthMode:
    """Detect current authentication mode.

    If callers are expected to authenticate, the project uses database-backed
    caller API keys. When no external auth is required (e.g. local stdio-like
    workflows), mode falls back to NONE.
    """
    return AuthMode.DATABASE_API_KEY


def get_auth_mode() -> AuthMode:
    """Get the current authentication mode."""
    global _detected_auth_mode
    if _detected_auth_mode is None:
        _detected_auth_mode = _detect_auth_mode()
        logger.info(f"Authentication mode: {_detected_auth_mode.value}")
    return _detected_auth_mode


def reset_auth_config() -> None:
    """Reset cached auth configuration (for testing)."""
    global _detected_auth_mode
    _detected_auth_mode = None


def is_auth_required() -> bool:
    """Check whether HTTP layer requires caller authentication."""
    return get_auth_mode() != AuthMode.NONE


def extract_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    """Extract token from Authorization header.

    Supports Bearer token format: "Bearer <token>".
    """
    if not auth_header:
        return None

    prefix = "Bearer "
    if auth_header.startswith(prefix):
        return auth_header[len(prefix):].strip()

    return auth_header.strip()


def _get_caller_by_api_key(token: str) -> Optional[dict]:
    """Get caller info by API key token if valid and active."""
    try:
        from mineru_mcp.config import get_config
        from mineru_mcp.task_queue import TaskDatabase

        config = get_config()
        db = TaskDatabase(db_path=config.db_path)

        caller = db.get_caller_by_api_key(token)
        if caller is None:
            return None

        if caller.get("disabled", 0) == 1:
            return None

        expires_at = caller.get("expires_at")
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_dt:
                return None

        return caller
    except Exception as e:
        logger.error(f"Error getting caller by API key: {e}")
        return None


def get_caller_by_api_key(token: str) -> Optional[dict]:
    """Public wrapper for caller lookup."""
    return _get_caller_by_api_key(token)


def validate_token(provided_token: Optional[str]) -> Tuple[bool, Optional[MCPError]]:
    """Validate provided authentication token."""
    token = extract_token_from_header(provided_token) if provided_token else None
    if not token:
        return False, auth_missing()

    caller = _get_caller_by_api_key(token)
    if caller is None:
        logger.debug("API key not found in database")
        return False, auth_invalid()

    try:
        from mineru_mcp.config import get_config
        from mineru_mcp.task_queue import TaskDatabase

        config = get_config()
        db = TaskDatabase(db_path=config.db_path)
        db.update_caller_last_used(caller["caller_id"])
    except Exception as e:
        logger.error(f"Error updating caller last_used_at: {e}")
        return False, auth_invalid()

    return True, None


def check_auth_header(auth_header: Optional[str]) -> Optional[MCPError]:
    """Check Authorization header for valid caller API key."""
    _, error = validate_token(auth_header)
    return error


def generate_token(length: int = 32) -> str:
    """Generate a secure random token for caller bootstrap."""
    return secrets.token_hex(length)


def resolve_principal(
    auth_header: Optional[str],
    proxy_headers: Optional[dict[str, str]] = None,
) -> CurrentPrincipal:
    """Resolve authenticated principal from caller API key.

    `proxy_headers` is accepted only to preserve call-site signature stability.
    """
    del proxy_headers
    token = extract_token_from_header(auth_header)
    if not token:
        logger.warning("Caller API key mode requires authentication token")
        raise auth_missing()

    caller = _get_caller_by_api_key(token)
    if caller is None:
        logger.warning("Unknown API key from database")
        raise auth_invalid()

    return CurrentPrincipal(
        principal_id=caller["caller_id"],
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name=caller["name"],
        caller_id=caller["caller_id"],
    )


def get_current_principal_id(auth_header: Optional[str]) -> str:
    """Convenience function to get the current principal ID."""
    try:
        principal = resolve_principal(auth_header)
        return principal.principal_id
    except MCPError:
        return "anonymous"


def get_current_principal_safe(auth_header: Optional[str]) -> CurrentPrincipal:
    """Get current principal, returning anonymous on failure instead of raising."""
    try:
        return resolve_principal(auth_header)
    except MCPError as e:
        logger.warning(f"Auth failed: {e.message}")
        return CurrentPrincipal(
            principal_id="anonymous",
            principal_type=PrincipalType.UNKNOWN,
            role=PrincipalRole.USER,
        )


def get_stdio_principal() -> CurrentPrincipal:
    """Principal used by stdio/local MCP execution without HTTP auth."""
    return DEFAULT_SINGLE_USER_PRINCIPAL


def print_generated_token() -> None:
    """Print a generated caller-style token for manual bootstrap."""
    token = generate_token()
    print(f"Generated caller token: {token}")
    print("Store it in callers table via admin console or bootstrap script.")


if __name__ == "__main__":
    print_generated_token()
