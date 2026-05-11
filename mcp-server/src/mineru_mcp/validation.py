"""
Input Validation Module

Provides validation functions for file paths, file types, and other inputs
to prevent security issues like path traversal attacks.
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

from mineru_mcp.config import VALID_BACKENDS


def _parse_size(size_str: str) -> int:
    """Parse size string to bytes.
    
    Supports formats: '500MB', '1GB', '1024KB', or plain number.
    
    Args:
        size_str: Size string like '500MB' or '1073741824'.
        
    Returns:
        Size in bytes.
    """
    size_str = size_str.strip().upper()
    
    multipliers = {
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
    }
    
    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            try:
                value = int(size_str[:-len(suffix)])
                return value * multiplier
            except ValueError:
                break
    
    try:
        return int(size_str)
    except ValueError:
        return 500 * 1024 * 1024


MAX_FILE_SIZE = _parse_size(os.getenv("MCP_MAX_UPLOAD_SIZE", "500MB"))

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

DEFAULT_ALLOWED_DIRS = [
    Path("/app/input"),
    Path("/app/data"),
    Path.cwd(),
]


class ValidationError(Exception):
    """Validation error with structured error code."""
    
    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "error_code": self.code,
            "error_message": self.message,
            "error_details": self.details,
        }


# Error codes
ERROR_FILE_NOT_FOUND = "FILE_NOT_FOUND"
ERROR_PATH_TRAVERSAL = "PATH_TRAVERSAL"
ERROR_FILE_TOO_LARGE = "FILE_TOO_LARGE"
ERROR_INVALID_EXTENSION = "INVALID_EXTENSION"
ERROR_SYMLINK_NOT_ALLOWED = "SYMLINK_NOT_ALLOWED"
ERROR_PATH_NOT_ABSOLUTE = "PATH_NOT_ABSOLUTE"
ERROR_OUTSIDE_ALLOWED_DIRS = "OUTSIDE_ALLOWED_DIRS"
ERROR_INVALID_TASK_ID = "INVALID_TASK_ID"
ERROR_INVALID_BACKEND = "INVALID_BACKEND"
ERROR_INVALID_PAGE_RANGE = "INVALID_PAGE_RANGE"


def get_allowed_dirs() -> List[Path]:
    """Get allowed directories from environment or defaults.
    
    Returns:
        List of allowed directory paths.
    """
    env_dirs = os.getenv("MCP_ALLOWED_DIRS", "")
    if env_dirs:
        dirs = [Path(d.strip()) for d in env_dirs.split(",") if d.strip()]
        return dirs
    return DEFAULT_ALLOWED_DIRS


def validate_file_path(
    file_path: str,
    allowed_dirs: Optional[List[Path]] = None,
    max_size: int = MAX_FILE_SIZE,
    allowed_extensions: Optional[set] = None,
) -> Path:
    """Validate a file path for security issues.
    
    This function checks for:
    - Path existence
    - Path traversal attacks
    - Symlink attacks
    - File size limits
    - File extension restrictions
    - Directory restrictions
    
    Args:
        file_path: The file path to validate.
        allowed_dirs: List of allowed directories. Defaults to get_allowed_dirs().
        max_size: Maximum file size in bytes. Defaults to MAX_FILE_SIZE.
        allowed_extensions: Allowed file extensions. Defaults to ALLOWED_EXTENSIONS.
        
    Returns:
        Resolved absolute Path object if validation passes.
        
    Raises:
        ValidationError: If validation fails with specific error code.
    """
    if allowed_dirs is None:
        allowed_dirs = get_allowed_dirs()
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS
    
    # 1. Convert to Path object
    path = Path(file_path)
    
    # 2. Check if path is absolute (required for security)
    if not path.is_absolute():
        # Try to resolve relative path
        try:
            path = path.resolve()
        except Exception as e:
            raise ValidationError(
                ERROR_PATH_NOT_ABSOLUTE,
                "Could not resolve path to absolute",
                {"original_path": file_path, "error": str(e)},
            )
    
    # 3. Resolve the path to get the real path (handles symlinks)
    try:
        real_path = path.resolve()
    except Exception as e:
        raise ValidationError(
            ERROR_FILE_NOT_FOUND,
            "Path could not be resolved",
            {"path": file_path, "error": str(e)},
        )
    
    # 4. Check for symlink (optional security measure)
    if path.is_symlink():
        # Allow symlinks only if they point to allowed directories
        symlink_allowed = os.getenv("MCP_ALLOW_SYMLINKS", "false").lower() == "true"
        if not symlink_allowed:
            raise ValidationError(
                ERROR_SYMLINK_NOT_ALLOWED,
                "Symbolic links are not allowed",
                {"path": file_path, "real_path": str(real_path)},
            )
    
    # 5. Check if file exists
    if not real_path.exists():
        raise ValidationError(
            ERROR_FILE_NOT_FOUND,
            "File not found",
            {"path": file_path, "resolved_path": str(real_path)},
        )
    
    # 6. Check if it's a file (not a directory)
    if not real_path.is_file():
        raise ValidationError(
            ERROR_FILE_NOT_FOUND,
            "Path is not a file",
            {"path": file_path, "resolved_path": str(real_path)},
        )
    
    # 7. Check path traversal (must be within allowed directories)
    is_allowed = False
    for allowed_dir in allowed_dirs:
        try:
            # Resolve allowed dir too
            allowed_dir_resolved = allowed_dir.resolve()
            if real_path.is_relative_to(allowed_dir_resolved):
                is_allowed = True
                break
        except Exception:
            # If allowed dir doesn't exist, skip it
            continue
    
    if not is_allowed:
        raise ValidationError(
            ERROR_OUTSIDE_ALLOWED_DIRS,
            "File path is outside allowed directories",
            {
                "path": file_path,
                "resolved_path": str(real_path),
                "allowed_dirs": [str(d) for d in allowed_dirs],
            },
        )
    
    # 8. Check file extension
    extension = real_path.suffix.lower()
    if extension not in allowed_extensions:
        raise ValidationError(
            ERROR_INVALID_EXTENSION,
            f"File extension '{extension}' is not allowed",
            {
                "path": file_path,
                "extension": extension,
                "allowed_extensions": list(allowed_extensions),
            },
        )
    
    # 9. Check file size
    try:
        file_size = real_path.stat().st_size
        if file_size > max_size:
            raise ValidationError(
                ERROR_FILE_TOO_LARGE,
                f"File size ({file_size} bytes) exceeds maximum ({max_size} bytes)",
                {
                    "path": file_path,
                    "size": file_size,
                    "max_size": max_size,
                },
            )
    except OSError as e:
        raise ValidationError(
            ERROR_FILE_NOT_FOUND,
            "Could not get file size",
            {"path": file_path, "error": str(e)},
        )
    
    # Log successful validation
    logger.debug(f"File path validated: {real_path}")
    
    return real_path


def validate_task_id(task_id: str) -> str:
    """Validate a task ID format.
    
    Args:
        task_id: The task ID to validate.
        
    Returns:
        The validated task ID.
        
    Raises:
        ValidationError: If task ID is invalid.
    """
    # Task IDs should be alphanumeric with hyphens/underscores
    # Typical format: UUID or similar
    if not task_id:
        raise ValidationError(
            "INVALID_TASK_ID",
            "Task ID cannot be empty",
            {"task_id": task_id},
        )
    
    # Basic format check (allow UUIDs and similar formats)
    if not re.match(r'^[a-zA-Z0-9_-]+$', task_id):
        raise ValidationError(
            "INVALID_TASK_ID",
            "Task ID contains invalid characters",
            {"task_id": task_id, "allowed_pattern": "[a-zA-Z0-9_-]+"},
        )
    
    # Length check (UUID is 36 chars with hyphens, 32 without)
    if len(task_id) > 64:
        raise ValidationError(
            "INVALID_TASK_ID",
            "Task ID is too long",
            {"task_id": task_id, "max_length": 64},
        )
    
    return task_id


def validate_backend(backend: str) -> str:
    """Validate a backend name.
    
    Args:
        backend: The backend name to validate.
        
    Returns:
        The validated backend name.
        
    Raises:
        ValidationError: If backend is invalid.
    """
    if backend not in VALID_BACKENDS:
        raise ValidationError(
            "INVALID_BACKEND",
            f"Backend '{backend}' is not valid",
            {"backend": backend, "valid_backends": list(VALID_BACKENDS)},
        )
    
    return backend


def validate_language(lang: str) -> str:
    """Validate a language code.
    
    Args:
        lang: The language code to validate.
        
    Returns:
        The validated language code.
        
    Raises:
        ValidationError: If language is invalid.
    """
    VALID_LANGS = {
        "ch", "en", "korean", "japan", "chinese", "english",
        "zh", "cn", "ko", "ja", "ru", "de", "fr", "es", "pt", "it",
    }
    
    lang_lower = lang.lower()
    if lang_lower not in VALID_LANGS:
        # Allow unknown languages with a warning (MinerU may support more)
        logger.warning(f"Unknown language code: {lang}")
    
    return lang_lower


def validate_upload_file(
    filename: Optional[str],
    content: bytes,
    max_size: int = MAX_FILE_SIZE,
    allowed_extensions: Optional[set] = None,
) -> str:
    """Validate an uploaded file.
    
    Args:
        filename: Original filename (optional).
        content: File content as bytes.
        max_size: Maximum file size in bytes. Defaults to MAX_FILE_SIZE.
        allowed_extensions: Allowed file extensions. Defaults to ALLOWED_EXTENSIONS.
        
    Returns:
        Sanitized filename with extension.
        
    Raises:
        ValidationError: If validation fails.
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS
    
    # 1. Check content size
    if len(content) > max_size:
        raise ValidationError(
            ERROR_FILE_TOO_LARGE,
            f"File size ({len(content)} bytes) exceeds maximum ({max_size} bytes)",
            {
                "size": len(content),
                "max_size": max_size,
            },
        )
    
    # 2. Check content is not empty
    if len(content) == 0:
        raise ValidationError(
            "EMPTY_FILE",
            "Uploaded file is empty",
            {"filename": filename},
        )
    
    # 3. Extract and validate extension
    if filename:
        extension = Path(filename).suffix.lower()
        if extension not in allowed_extensions:
            raise ValidationError(
                ERROR_INVALID_EXTENSION,
                f"File extension '{extension}' is not allowed",
                {
                    "filename": filename,
                    "extension": extension,
                    "allowed_extensions": list(allowed_extensions),
                },
            )
        
        # Sanitize filename (remove path components)
        safe_filename = Path(filename).name
        
        # Validate filename doesn't contain dangerous characters
        if not re.match(r'^[a-zA-Z0-9_\-. ]+$', safe_filename):
            # Replace dangerous characters
            safe_filename = re.sub(r'[^\w\-. ]', '_', safe_filename)
        
        return safe_filename
    else:
        # No filename, return default
        return "input.pdf"


def validate_page_range(
    start_page_id: int,
    end_page_id: int,
) -> Tuple[int, int]:
    """Validate page range parameters.
    
    Args:
        start_page_id: Starting page (0-indexed).
        end_page_id: Ending page (0-indexed).
        
    Returns:
        Tuple of validated (start_page_id, end_page_id).
        
    Raises:
        ValidationError: If page range is invalid.
    """
    if start_page_id < 0:
        raise ValidationError(
            "INVALID_PAGE_RANGE",
            "Start page cannot be negative",
            {"start_page_id": start_page_id},
        )
    
    if end_page_id < start_page_id:
        raise ValidationError(
            "INVALID_PAGE_RANGE",
            "End page must be greater than or equal to start page",
            {"start_page_id": start_page_id, "end_page_id": end_page_id},
        )
    
    # Reasonable upper limit (most PDFs won't have more than 10000 pages)
    if end_page_id > 99999:
        raise ValidationError(
            "INVALID_PAGE_RANGE",
            "End page exceeds maximum allowed value",
            {"end_page_id": end_page_id, "max_allowed": 99999},
        )
    
    return start_page_id, end_page_id
