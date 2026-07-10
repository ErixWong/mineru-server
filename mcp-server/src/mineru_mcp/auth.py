"""
Authentication Module

Provides Bearer Token authentication for HTTP mode MCP Server.
Supports multiple authentication modes:
- Single-user mode (MINERU_SINGLE_USER_MODE=true)
- Multi-user API Key mapping (MINERU_API_KEYS_FILE)
- Trusted proxy header (MINERU_TRUSTED_PROXY_HEADER)
- Legacy shared token (MCP_HTTP_AUTH_TOKEN) - only for backward compatibility
"""

import os
import secrets
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
from enum import Enum

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
    SINGLE_USER = "single_user"       # Single user mode - no isolation
    API_KEY_MAP = "api_key_map"        # Multi-user with API key mapping
    TRUSTED_PROXY = "trusted_proxy"    # Multi-user with trusted proxy header
    LEGACY_SHARED = "legacy_shared"    # Legacy single shared token (backward compat)
    NONE = "none"                      # No authentication required


# Configuration
TOKEN_MIN_LENGTH = 16  # Minimum token length for security

# Mode detection - determine auth mode based on configuration
_API_KEYS_FILE = os.getenv("MINERU_API_KEYS_FILE", "")
_PROXY_USER_HEADER = os.getenv("MINERU_TRUSTED_PROXY_HEADER", "")
_ADMIN_API_KEYS = os.getenv("MINERU_ADMIN_API_KEYS", "")
_LEGACY_TOKEN = os.getenv("MCP_HTTP_AUTH_TOKEN", "")
_SINGLE_USER_MODE = os.getenv("MINERU_SINGLE_USER_MODE", "false").lower() == "true"


def _detect_auth_mode() -> AuthMode:
    """Detect the current authentication mode based on configuration.
    
    Priority (first match wins):
    1. SINGLE_USER - explicitly enabled
    2. API_KEY_MAP - API keys file exists and has entries
    3. TRUSTED_PROXY - proxy header configured
    4. LEGACY_SHARED - legacy token configured
    5. NONE - nothing configured
    
    When multiple sources are configured simultaneously, the highest-priority
    source wins and a warning is emitted for each ignored source.
    """
    # Collect all active configuration sources for conflict detection
    active_sources: list[str] = []
    
    if _SINGLE_USER_MODE:
        active_sources.append("SINGLE_USER")
    
    has_api_keys = False
    if _API_KEYS_FILE and Path(_API_KEYS_FILE).exists():
        try:
            with open(_API_KEYS_FILE, "r", encoding="utf-8") as f:
                keys = json.load(f)
                if keys and isinstance(keys, dict) and len(keys) > 0:
                    has_api_keys = True
                    active_sources.append("API_KEY_MAP")
        except (json.JSONDecodeError, IOError):
            pass
    
    if _PROXY_USER_HEADER:
        active_sources.append("TRUSTED_PROXY")
    
    if _LEGACY_TOKEN:
        active_sources.append("LEGACY_SHARED")
    
    # Determine winning mode (first match)
    if _SINGLE_USER_MODE:
        winner = AuthMode.SINGLE_USER
    elif has_api_keys:
        winner = AuthMode.API_KEY_MAP
    elif _PROXY_USER_HEADER:
        winner = AuthMode.TRUSTED_PROXY
    elif _LEGACY_TOKEN:
        winner = AuthMode.LEGACY_SHARED
    else:
        winner = AuthMode.NONE
    
    # Warn about conflicting configurations (only if more than one source active)
    if len(active_sources) > 1:
        ignored = [s for s in active_sources if s != winner.value.upper()]
        logger.warning(
            f"Multiple auth sources configured: {', '.join(active_sources)}. "
            f"Using '{winner.value}' (highest priority). "
            f"Ignored: {', '.join(ignored)}."
        )
    
    return winner


# Cache the detected auth mode
_detected_auth_mode: Optional[AuthMode] = None


def get_auth_mode() -> AuthMode:
    """Get the current authentication mode."""
    global _detected_auth_mode
    if _detected_auth_mode is None:
        _detected_auth_mode = _detect_auth_mode()
        logger.info(f"Authentication mode: {_detected_auth_mode.value}")
    return _detected_auth_mode


def reset_auth_config() -> None:
    """Reset all cached auth configuration (for testing).
    
    Re-reads environment variables and clears the detected auth mode
    so that the next call to get_auth_mode() re-detects based on the
    current environment.
    """
    global _detected_auth_mode, _API_KEYS_FILE, _PROXY_USER_HEADER
    global _ADMIN_API_KEYS, _LEGACY_TOKEN, _SINGLE_USER_MODE
    global _api_keys_cache, _admin_keys_cache
    
    _detected_auth_mode = None
    _API_KEYS_FILE = os.getenv("MINERU_API_KEYS_FILE", "")
    _PROXY_USER_HEADER = os.getenv("MINERU_TRUSTED_PROXY_HEADER", "")
    _ADMIN_API_KEYS = os.getenv("MINERU_ADMIN_API_KEYS", "")
    _LEGACY_TOKEN = os.getenv("MCP_HTTP_AUTH_TOKEN", "")
    _SINGLE_USER_MODE = os.getenv("MINERU_SINGLE_USER_MODE", "false").lower() == "true"
    _api_keys_cache = None
    _admin_keys_cache = None


def is_auth_required() -> bool:
    """Check if authentication is required.
    
    Returns:
        True if authentication mode is not NONE.
    """
    mode = get_auth_mode()
    return mode != AuthMode.NONE


def _load_api_keys() -> Dict[str, dict]:
    """Load API key to principal mappings from file."""
    if not _API_KEYS_FILE:
        return {}
    
    keys_file = Path(_API_KEYS_FILE)
    if not keys_file.exists():
        return {}
    
    try:
        with open(keys_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load API keys file: {e}")
        return {}


def _get_admin_keys() -> set:
    """Get set of admin API keys from environment."""
    if not _ADMIN_API_KEYS:
        return set()
    return {key.strip() for key in _ADMIN_API_KEYS.split(",") if key.strip()}


# Cached API keys (lazy loaded)
_api_keys_cache: Optional[Dict[str, dict]] = None
_admin_keys_cache: Optional[set] = None


def _get_api_keys() -> Dict[str, dict]:
    """Get API keys with caching."""
    global _api_keys_cache
    if _api_keys_cache is None:
        _api_keys_cache = _load_api_keys()
    return _api_keys_cache


def _get_admin_keys_set() -> set:
    """Get admin keys with caching."""
    global _admin_keys_cache
    if _admin_keys_cache is None:
        _admin_keys_cache = _get_admin_keys()
    return _admin_keys_cache


def extract_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    """Extract token from Authorization header.
    
    Supports Bearer token format: "Bearer <token>"
    
    Args:
        auth_header: Authorization header value.
        
    Returns:
        Extracted token, or None if not found.
    """
    if not auth_header:
        return None
    
    # Check Bearer prefix
    prefix = "Bearer "
    if auth_header.startswith(prefix):
        return auth_header[len(prefix):].strip()
    
    # No Bearer prefix, treat entire header as token
    return auth_header.strip()


def validate_token(provided_token: Optional[str]) -> Tuple[bool, Optional[MCPError]]:
    """Validate provided authentication token based on current auth mode.
    
    Args:
        provided_token: Token provided by client.
        
    Returns:
        Tuple of (is_valid, error).
    """
    mode = get_auth_mode()
    token = extract_token_from_header(provided_token) if provided_token else None
    
    # No token provided
    if not token:
        if mode in (AuthMode.NONE, AuthMode.TRUSTED_PROXY):
            return True, None  # No token required (proxy header is the auth source)
        return False, auth_missing()
    
    # Validate based on mode
    if mode == AuthMode.SINGLE_USER:
        # Single user mode - accept any token or no token
        return True, None
    
    elif mode == AuthMode.API_KEY_MAP:
        # API Key mapping mode - check against mapped keys and admin keys
        admin_keys = _get_admin_keys_set()
        if token in admin_keys:
            return True, None
        api_keys = _get_api_keys()
        if token in api_keys:
            return True, None
        # Not found in any key store
        return False, auth_invalid()
    
    elif mode == AuthMode.TRUSTED_PROXY:
        # Proxy mode - proxy header is the primary auth source
        # If a token is also provided, it's accepted for backward compat
        return True, None
    
    elif mode == AuthMode.LEGACY_SHARED:
        # Legacy mode - only accept the shared token
        if not _LEGACY_TOKEN:
            return True, None  # Shouldn't happen but safety check
        if secrets.compare_digest(token, _LEGACY_TOKEN):
            return True, None
        return False, auth_invalid()
    
    elif mode == AuthMode.NONE:
        return True, None
    
    # Fallback
    return True, None


def check_auth_header(auth_header: Optional[str]) -> Optional[MCPError]:
    """Check Authorization header for valid token.
    
    Args:
        auth_header: Authorization header value.
        
    Returns:
        None if authenticated, MCPError if not.
    """
    is_valid, error = validate_token(auth_header)
    return error


def generate_token(length: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_hex(length)


def is_single_user_mode() -> bool:
    """Check if running in single-user mode."""
    return get_auth_mode() == AuthMode.SINGLE_USER


def resolve_principal(
    auth_header: Optional[str],
    proxy_headers: Optional[Dict[str, str]] = None,
) -> CurrentPrincipal:
    """Resolve the current principal from authentication context.
    
    This function determines the authenticated user based on the current auth mode.
    
    Args:
        auth_header: The Authorization header value.
        proxy_headers: Optional dict of proxy headers (for trusted proxy auth).
        
    Returns:
        CurrentPrincipal object representing the authenticated user.
        
    Raises:
        MCPError: If authentication fails in multi-user mode.
    """
    mode = get_auth_mode()
    token = extract_token_from_header(auth_header)
    
    # Handle each mode explicitly
    if mode == AuthMode.SINGLE_USER:
        logger.debug("Single-user mode: using default principal")
        return DEFAULT_SINGLE_USER_PRINCIPAL
    
    elif mode == AuthMode.API_KEY_MAP:
        # Must have a valid token
        if not token:
            # No token in API key mode - this is an error
            logger.warning("API Key mode requires authentication token")
            raise auth_missing()
        
        # Check admin keys first
        admin_keys = _get_admin_keys_set()
        if token in admin_keys:
            logger.debug(f"Admin key authenticated")
            return CurrentPrincipal(
                principal_id="admin",
                principal_type=PrincipalType.API_KEY,
                role=PrincipalRole.ADMIN,
                display_name="Admin User",
            )
        
        # Check API key mapping
        api_keys = _get_api_keys()
        if token in api_keys:
            key_info = api_keys[token]
            role = PrincipalRole.ADMIN if key_info.get("role") == "admin" else PrincipalRole.USER
            logger.debug(f"API key authenticated: principal_id={key_info.get('principal_id')}, role={role.value}")
            return CurrentPrincipal(
                principal_id=key_info.get("principal_id", "unknown"),
                principal_type=PrincipalType.API_KEY,
                role=role,
                tenant_id=key_info.get("tenant_id"),
                display_name=key_info.get("display_name"),
            )
        
        # Token not found in API key mode
        logger.warning(f"Unknown API key")
        raise auth_invalid()
    
    elif mode == AuthMode.TRUSTED_PROXY:
        # Proxy mode: proxy header is the primary auth source
        # Token is NOT required; only used for optional backward compat fallback
        
        # Normalize proxy header key to lowercase for matching
        proxy_header_key = _PROXY_USER_HEADER.lower() if _PROXY_USER_HEADER else ""
        
        # Normalize proxy_headers keys to lowercase
        normalized_proxy_headers = {}
        if proxy_headers:
            for k, v in proxy_headers.items():
                normalized_proxy_headers[k.lower()] = v
        
        proxy_user = normalized_proxy_headers.get(proxy_header_key)
        if proxy_user:
            logger.debug(f"Proxy header authenticated: principal_id={proxy_user}")
            return CurrentPrincipal(
                principal_id=proxy_user,
                principal_type=PrincipalType.PROXY_HEADER,
                role=PrincipalRole.USER,
            )
        
        # No proxy header found — check legacy token fallback if provided
        if token and _LEGACY_TOKEN and secrets.compare_digest(token, _LEGACY_TOKEN):
            logger.debug("Legacy token fallback in proxy mode")
            return DEFAULT_SINGLE_USER_PRINCIPAL
        
        # No valid principal found
        logger.warning(f"No valid proxy header found (expected: {_PROXY_USER_HEADER})")
        raise auth_invalid()
    
    elif mode == AuthMode.LEGACY_SHARED:
        # Legacy mode - only accept shared token
        if not token:
            logger.warning("Legacy mode requires authentication token")
            raise auth_missing()
        
        if not _LEGACY_TOKEN:
            return DEFAULT_SINGLE_USER_PRINCIPAL
            
        if secrets.compare_digest(token, _LEGACY_TOKEN):
            logger.debug("Legacy token authenticated")
            return DEFAULT_SINGLE_USER_PRINCIPAL
        
        logger.warning(f"Invalid legacy token")
        raise auth_invalid()
    
    elif mode == AuthMode.NONE:
        # No auth required - use default
        return DEFAULT_SINGLE_USER_PRINCIPAL
    
    # Should not reach here
    logger.error(f"Unknown auth mode: {mode}")
    raise auth_invalid()


def get_current_principal_id(auth_header: Optional[str]) -> str:
    """Convenience function to get the current principal ID.
    
    Args:
        auth_header: The Authorization header value.
        
    Returns:
        The principal ID string.
    """
    try:
        principal = resolve_principal(auth_header)
        return principal.principal_id
    except MCPError:
        return "anonymous"


def get_current_principal_safe(auth_header: Optional[str]) -> CurrentPrincipal:
    """Get current principal, returning anonymous on failure instead of raising.
    
    This is a safe wrapper for cases where we need to handle auth failures gracefully.
    """
    try:
        return resolve_principal(auth_header)
    except MCPError as e:
        logger.warning(f"Auth failed: {e.message}")
        return CurrentPrincipal(
            principal_id="anonymous",
            principal_type=PrincipalType.UNKNOWN,
            role=PrincipalRole.USER,
        )


# CLI helper for token generation
def print_generated_token() -> None:
    """Print a generated token for configuration."""
    token = generate_token()
    print(f"Generated auth token: {token}")
    print(f"Add to environment: MCP_HTTP_AUTH_TOKEN={token}")
    print(f"Or add to .env file: MCP_HTTP_AUTH_TOKEN={token}")


if __name__ == "__main__":
    print_generated_token()