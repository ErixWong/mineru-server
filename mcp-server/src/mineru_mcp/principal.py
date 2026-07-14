"""
Principal Model

Defines the CurrentPrincipal object that represents the authenticated user
for authorization purposes. This is the foundation for task ownership isolation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from contextvars import ContextVar


class PrincipalType(str, Enum):
    """Types of principals that can own tasks."""
    API_KEY = "api_key"           # Authenticated via API key mapping
    PROXY_HEADER = "proxy_header" # Authenticated via trusted proxy header
    SINGLE_USER = "single_user"   # Single-user mode with default principal
    UNKNOWN = "unknown"           # Unknown/unauthenticated


class PrincipalRole(str, Enum):
    """Role of the principal."""
    USER = "user"         # Regular user - can only access own tasks
    ADMIN = "admin"       # Admin - can access all tasks


# Context variable for storing the current principal across the request
# This allows propagating principal from HTTP layer to MCP tools
_current_principal_var: ContextVar[Optional["CurrentPrincipal"]] = ContextVar(
    "current_principal", 
    default=None
)


def set_current_principal(principal: "CurrentPrincipal") -> None:
    """Set the current principal for this request context.
    
    Args:
        principal: The principal to set.
    """
    _current_principal_var.set(principal)


def get_current_principal() -> Optional["CurrentPrincipal"]:
    """Get the current principal from the request context.
    
    Returns:
        The current principal, or None if not set.
    """
    return _current_principal_var.get()


def clear_current_principal() -> None:
    """Clear the current principal from the request context."""
    _current_principal_var.set(None)


@dataclass
class CurrentPrincipal:
    """Represents the currently authenticated principal for authorization.
    
    This object is created during authentication and passed through to
    service layers for authorization decisions.
    
    Attributes:
        principal_id: Unique identifier for this principal
        principal_type: Source type of the principal (api_key, proxy_header, etc.)
        role: Role of the principal (user or admin)
        tenant_id: Optional tenant identifier for multi-tenant systems
        display_name: Optional human-readable name for display purposes
        caller_id: Optional caller identifier from callers table (for DATABASE_API_KEY mode)
    """
    principal_id: str
    principal_type: PrincipalType
    role: PrincipalRole = PrincipalRole.USER
    tenant_id: Optional[str] = None
    display_name: Optional[str] = None
    caller_id: Optional[str] = None
    
    def is_admin(self) -> bool:
        """Check if this principal has admin privileges."""
        return self.role == PrincipalRole.ADMIN
    
    def is_single_user_mode(self) -> bool:
        """Check if running in single-user mode."""
        return self.principal_type == PrincipalType.SINGLE_USER
    
    def __str__(self) -> str:
        return f"CurrentPrincipal(id={self.principal_id}, type={self.principal_type.value}, role={self.role.value}, caller_id={self.caller_id})"


# Default principal for single-user mode
DEFAULT_SINGLE_USER_PRINCIPAL = CurrentPrincipal(
    principal_id="local-default",
    principal_type=PrincipalType.SINGLE_USER,
    role=PrincipalRole.USER,
    display_name="Local User"
)