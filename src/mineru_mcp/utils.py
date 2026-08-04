"""
MCP Server Utility Functions

Shared helpers used by both MCP tools (server.py) and REST API (api.py).
"""

import base64
import tempfile
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Optional

from mineru_mcp.validation import ERROR_FILE_TOO_LARGE, MAX_FILE_SIZE, ValidationError


def save_base64_file(
    file_base64: str,
    file_name: Optional[str] = None,
    temp_dir: Optional[str] = None,
) -> Path:
    """Save base64-encoded file content to a temporary file.
    
    Args:
        file_base64: Base64-encoded file content.
        file_name: Optional file name (for extension detection).
        temp_dir: Optional temporary directory (defaults to system temp).
        
    Returns:
        Path to the saved temporary file.
        
    Raises:
        ValueError: If base64 content is invalid.
    """
    try:
        file_bytes = base64.b64decode(file_base64)
    except Exception as e:
        raise ValueError(f"Invalid base64 content: {e}")
    
    suffix = Path(file_name).suffix if file_name else ".pdf"
    unique_name = f"{uuid.uuid4()}{suffix}"
    
    if temp_dir:
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)
    else:
        temp_path = Path(tempfile.gettempdir()) / "mineru_mcp_upload"
        temp_path.mkdir(parents=True, exist_ok=True)
    
    file_path = temp_path / unique_name
    file_path.write_bytes(file_bytes)
    
    return file_path


def cleanup_temp_file(file_path: Path) -> None:
    """Clean up temporary file.
    
    Args:
        file_path: Path to the temporary file.
    """
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass


def save_upload_stream(
    source: BinaryIO,
    file_name: Optional[str] = None,
    max_size: int = MAX_FILE_SIZE,
) -> Path:
    """Stream an uploaded file into a temporary path with a size limit."""
    suffix = Path(file_name).suffix if file_name else ".pdf"
    temp_path: Optional[Path] = None
    total_size = 0

    try:
        with tempfile.NamedTemporaryFile(
            prefix="mineru-upload-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := source.read(1024 * 1024):
                if total_size + len(chunk) > max_size:
                    raise ValidationError(
                        ERROR_FILE_TOO_LARGE,
                        f"File size exceeds maximum ({max_size} bytes)",
                        {"max_size": max_size},
                    )
                temp_file.write(chunk)
                total_size += len(chunk)
    except Exception:
        if temp_path is not None:
            cleanup_temp_file(temp_path)
        raise

    return temp_path


def aggregate_markdown(result: dict[str, Any]) -> str:
    """Extract and concatenate markdown content from a task result.

    Args:
        result: Raw result dict from task processing.

    Returns:
        Aggregated markdown string from all pages/files.
    """
    markdown_content = ""
    if "results" in result:
        for file_name, file_result in result["results"].items():
            if "md_content" in file_result:
                markdown_content += f"\n---\n## {file_name}\n---\n\n"
                markdown_content += file_result["md_content"]
    return markdown_content.strip()


def extract_images(result: dict[str, Any]) -> dict[str, str]:
    """Extract all Base64 images from a task result.

    Args:
        result: Raw result dict from task processing.

    Returns:
        Dict mapping image filename to Base64 data URL.
    """
    all_images: dict[str, str] = {}
    if "results" in result:
        for file_result in result["results"].values():
            if "images" in file_result:
                all_images.update(file_result["images"])
    return all_images
