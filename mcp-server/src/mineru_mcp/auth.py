"""
Authentication Module

Provides Bearer Token authentication for HTTP mode MCP Server.
"""

import os
import secrets
from typing import Optional

from loguru import logger

from mineru_mcp.errors import auth_missing, auth_invalid, MCPError


# Token validation settings
TOKEN_MIN_LENGTH = 16  # Minimum token length for security


def get_auth_token() -> Optional[str]:
    """Get authentication token from environment.
    
    Returns:
        Authentication token if configured, None otherwise.
    """
    token = os.getenv("MCP_HTTP_AUTH_TOKEN")
    if token:
        # Validate token length
        if len(token) < TOKEN_MIN_LENGTH:
            logger.warning(
                f"Auth token is too short ({len(token)} chars). "
                f"Minimum recommended: {TOKEN_MIN_LENGTH} chars."
            )
        return token
    return None


def is_auth_required() -> bool:
    """Check if authentication is required.
    
    Returns:
        True if auth token is configured, False otherwise.
    """
    return get_auth_token() is not None


def validate_token(provided_token: Optional[str]) -> Optional[MCPError]:
    """Validate provided authentication token.
    
    Args:
        provided_token: Token provided by client.
        
    Returns:
        None if valid, MCPError if invalid or missing.
    """
    expected_token = get_auth_token()
    
    # No auth required
    if not expected_token:
        return None
    
    # Token missing
    if not provided_token:
        return auth_missing()
    
    # Token invalid (use secrets.compare_digest for timing-safe comparison)
    if not secrets.compare_digest(provided_token, expected_token):
        return auth_invalid()
    
    # Token valid
    return None


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


def check_auth_header(auth_header: Optional[str]) -> Optional[MCPError]:
    """Check Authorization header for valid token.
    
    Args:
        auth_header: Authorization header value.
        
    Returns:
        None if authenticated, MCPError if not.
    """
    if not is_auth_required():
        return None
    
    token = extract_token_from_header(auth_header)
    return validate_token(token)


def generate_token(length: int = 32) -> str:
    """Generate a secure random token.
    
    Args:
        length: Token length in bytes (will be hex-encoded, so 2x chars).
        
    Returns:
        Secure random token string.
    """
    return secrets.token_hex(length)


# CLI helper for token generation
def print_generated_token() -> None:
    """Print a generated token for configuration."""
    token = generate_token()
    print(f"Generated auth token: {token}")
    print(f"Add to environment: MCP_HTTP_AUTH_TOKEN={token}")
    print(f"Or add to .env file: MCP_HTTP_AUTH_TOKEN={token}")


if __name__ == "__main__":
    print_generated_token()
