"""
Structured Error Handling Module

Provides structured error codes and error response formatting for MCP tools.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ErrorCode(Enum):
    """Enumeration of all error codes used by MCP Server."""
    
    # File errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_EXTENSION = "INVALID_EXTENSION"
    SYMLINK_NOT_ALLOWED = "SYMLINK_NOT_ALLOWED"
    OUTSIDE_ALLOWED_DIRS = "OUTSIDE_ALLOWED_DIRS"
    
    # Task errors
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_FAILED = "TASK_FAILED"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    TASK_STILL_PROCESSING = "TASK_STILL_PROCESSING"
    INVALID_TASK_ID = "INVALID_TASK_ID"
    
    # Validation errors
    INVALID_BACKEND = "INVALID_BACKEND"
    INVALID_LANGUAGE = "INVALID_LANGUAGE"
    INVALID_PAGE_RANGE = "INVALID_PAGE_RANGE"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    
    # API errors
    MINERU_API_ERROR = "MINERU_API_ERROR"
    MINERU_API_TIMEOUT = "MINERU_API_TIMEOUT"
    MINERU_API_UNAVAILABLE = "MINERU_API_UNAVAILABLE"
    
    # Authentication errors
    AUTH_MISSING = "AUTH_MISSING"
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    
    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class MCPError:
    """Structured error for MCP tool responses.
    
    Attributes:
        code: Error code from ErrorCode enum.
        message: User-friendly error message.
        details: Additional details for debugging (not shown to user).
        http_status: Suggested HTTP status code for HTTP mode.
    """
    
    code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = None
    http_status: int = 400
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for JSON response.
        
        Returns:
            Dictionary with error information.
        """
        result = {
            "status": "error",
            "error_code": self.code.value,
            "error_message": self.message,
        }
        if self.details:
            # Only include safe details (no sensitive paths or tokens)
            safe_details = self._sanitize_details(self.details)
            if safe_details:
                result["error_details"] = safe_details
        return result
    
    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """Sanitize details to remove sensitive information.
        
        Args:
            details: Original details dictionary.
            
        Returns:
            Sanitized details dictionary.
        """
        # Keys that should be removed or masked
        sensitive_keys = {
            "api_key", "token", "password", "secret",
            "auth_header", "authorization",
        }
        
        safe_details = {}
        for key, value in details.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                continue  # Skip sensitive keys
            
            # Mask file paths (show only filename, not full path)
            if key_lower in ("path", "file_path", "resolved_path", "real_path"):
                if isinstance(value, str) and "/" in value or "\\" in value:
                    # Show only the filename
                    import os
                    safe_details[key] = os.path.basename(value)
                else:
                    safe_details[key] = value
            else:
                safe_details[key] = value
        
        return safe_details


# Pre-defined error instances for common cases

def file_not_found(path: str) -> MCPError:
    """Create FILE_NOT_FOUND error."""
    return MCPError(
        code=ErrorCode.FILE_NOT_FOUND,
        message="The specified file could not be found.",
        details={"path": path},
        http_status=404,
    )


def path_traversal(path: str) -> MCPError:
    """Create PATH_TRAVERSAL error."""
    return MCPError(
        code=ErrorCode.PATH_TRAVERSAL,
        message="File path is not allowed. Access denied.",
        details={"path": path},
        http_status=403,
    )


def file_too_large(size: int, max_size: int) -> MCPError:
    """Create FILE_TOO_LARGE error."""
    return MCPError(
        code=ErrorCode.FILE_TOO_LARGE,
        message=f"File size exceeds the maximum allowed limit.",
        details={"size": size, "max_size": max_size},
        http_status=413,
    )


def invalid_extension(extension: str, allowed: list[str]) -> MCPError:
    """Create INVALID_EXTENSION error."""
    return MCPError(
        code=ErrorCode.INVALID_EXTENSION,
        message=f"File type '{extension}' is not supported.",
        details={"extension": extension, "allowed_extensions": allowed},
        http_status=400,
    )


def task_not_found(task_id: str) -> MCPError:
    """Create TASK_NOT_FOUND error."""
    return MCPError(
        code=ErrorCode.TASK_NOT_FOUND,
        message="The specified task could not be found.",
        details={"task_id": task_id},
        http_status=404,
    )


def task_failed(task_id: str, reason: str) -> MCPError:
    """Create TASK_FAILED error."""
    return MCPError(
        code=ErrorCode.TASK_FAILED,
        message="The parsing task failed.",
        details={"task_id": task_id, "reason": reason},
        http_status=500,
    )


def task_timeout(task_id: str, timeout_seconds: float) -> MCPError:
    """Create TASK_TIMEOUT error."""
    return MCPError(
        code=ErrorCode.TASK_TIMEOUT,
        message="The parsing task timed out.",
        details={"task_id": task_id, "timeout_seconds": timeout_seconds},
        http_status=504,
    )


def task_still_processing(task_id: str) -> MCPError:
    """Create TASK_STILL_PROCESSING error."""
    return MCPError(
        code=ErrorCode.TASK_STILL_PROCESSING,
        message="The task is still processing. Please wait and try again.",
        details={"task_id": task_id},
        http_status=202,
    )


def invalid_backend(backend: str, valid_backends: list[str]) -> MCPError:
    """Create INVALID_BACKEND error."""
    return MCPError(
        code=ErrorCode.INVALID_BACKEND,
        message=f"Backend '{backend}' is not valid.",
        details={"backend": backend, "valid_backends": valid_backends},
        http_status=400,
    )


def mineru_api_error(status_code: int, message: str) -> MCPError:
    """Create MINERU_API_ERROR error."""
    return MCPError(
        code=ErrorCode.MINERU_API_ERROR,
        message="MinerU API returned an error.",
        details={"status_code": status_code, "api_message": message},
        http_status=502,
    )


def mineru_api_unavailable() -> MCPError:
    """Create MINERU_API_UNAVAILABLE error."""
    return MCPError(
        code=ErrorCode.MINERU_API_UNAVAILABLE,
        message="MinerU API is not available. Please check if the service is running.",
        details={},
        http_status=503,
    )


def auth_missing() -> MCPError:
    """Create AUTH_MISSING error."""
    return MCPError(
        code=ErrorCode.AUTH_MISSING,
        message="Authentication is required. Please provide a valid token.",
        details={},
        http_status=401,
    )


def auth_invalid() -> MCPError:
    """Create AUTH_INVALID error."""
    return MCPError(
        code=ErrorCode.AUTH_INVALID,
        message="The provided authentication token is invalid.",
        details={},
        http_status=401,
    )


def internal_error(error: str) -> MCPError:
    """Create INTERNAL_ERROR error."""
    return MCPError(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred. Please try again later.",
        details={"error": error},
        http_status=500,
    )


def unknown_error() -> MCPError:
    """Create UNKNOWN_ERROR error."""
    return MCPError(
        code=ErrorCode.UNKNOWN_ERROR,
        message="An unexpected error occurred.",
        details={},
        http_status=500,
    )


def from_exception(exc: Exception) -> MCPError:
    """Convert an exception to MCPError.
    
    Args:
        exc: The exception to convert.
        
    Returns:
        MCPError instance with appropriate code and message.
    """
    # Import ValidationError here to avoid circular import
    from mineru_mcp.validation import ValidationError
    
    if isinstance(exc, ValidationError):
        # Map ValidationError codes to ErrorCode enum
        code_map = {
            "FILE_NOT_FOUND": ErrorCode.FILE_NOT_FOUND,
            "PATH_TRAVERSAL": ErrorCode.PATH_TRAVERSAL,
            "FILE_TOO_LARGE": ErrorCode.FILE_TOO_LARGE,
            "INVALID_EXTENSION": ErrorCode.INVALID_EXTENSION,
            "SYMLINK_NOT_ALLOWED": ErrorCode.SYMLINK_NOT_ALLOWED,
            "OUTSIDE_ALLOWED_DIRS": ErrorCode.OUTSIDE_ALLOWED_DIRS,
            "INVALID_TASK_ID": ErrorCode.INVALID_TASK_ID,
            "INVALID_BACKEND": ErrorCode.INVALID_BACKEND,
            "INVALID_PAGE_RANGE": ErrorCode.INVALID_PAGE_RANGE,
        }
        code = code_map.get(exc.code, ErrorCode.INVALID_PARAMETER)
        return MCPError(
            code=code,
            message=exc.message,
            details=exc.details,
            http_status=400,
        )
    
    if isinstance(exc, FileNotFoundError):
        return file_not_found(str(exc))
    
    if isinstance(exc, ValueError):
        return MCPError(
            code=ErrorCode.INVALID_PARAMETER,
            message=str(exc),
            details={},
            http_status=400,
        )
    
    if isinstance(exc, TimeoutError):
        return MCPError(
            code=ErrorCode.TASK_TIMEOUT,
            message=str(exc),
            details={},
            http_status=504,
        )
    
    # Generic error
    return internal_error(str(exc))
