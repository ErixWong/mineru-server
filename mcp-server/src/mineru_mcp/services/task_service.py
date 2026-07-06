"""
Task Service Layer

Provides shared business logic for task operations that can be used
by both REST API (api.py) and MCP Protocol (server.py).

This is the first step in extracting shared service layer from duplicated
implementations across protocols.
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mineru_mcp.config import get_config, MCPConfig
from mineru_mcp.models import TaskStatus
from mineru_mcp.task_queue import TaskDatabase, FileManager
from mineru_mcp.validation import (
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
    MAX_FILE_SIZE,
    ERROR_FILE_TOO_LARGE,
)


class TaskService:
    """Shared service for task operations."""

    def __init__(self, db: TaskDatabase = None, file_manager: FileManager = None, config: MCPConfig = None):
        """Initialize task service with shared dependencies.

        Args:
            db: Task database instance. If not provided, creates default.
            file_manager: File manager instance. If not provided, creates default.
            config: MCP configuration. If not provided, loads from environment.
        """
        self.config = config or get_config()
        self.db = db or TaskDatabase(db_path=self.config.db_path)
        self.file_manager = file_manager or FileManager(output_root=self.config.output_root)

    def create_task_from_base64(
        self,
        file_base64: str,
        file_name: Optional[str] = None,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
    ) -> dict[str, Any]:
        """Create a task from base64-encoded file content.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            file_base64: Base64-encoded PDF file content.
            file_name: Optional file name for display and extension detection.
            backend: Parsing backend (defaults to config.default_backend).
            lang: Document language for OCR.
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            image_analysis: Enable VLM image analysis.
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).

        Returns:
            Task submission result dict with task_id, status, created_at.
        """
        effective_backend = backend if backend is not None else self.config.default_backend
        effective_server_url = server_url if server_url is not None else self.config.get_vlm_server_url()

        validated_backend = validate_backend(effective_backend)
        validated_lang = validate_language(lang)
        validate_page_range(start_page_id, end_page_id)

        logger.info(f"Decoding base64 file: {file_name or 'unnamed'}")

        file_bytes = base64.b64decode(file_base64)

        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValidationError(
                ERROR_FILE_TOO_LARGE,
                f"File size ({len(file_bytes)} bytes) exceeds maximum ({MAX_FILE_SIZE} bytes)",
                {"size": len(file_bytes), "max_size": MAX_FILE_SIZE},
            )

        task_id, task_dir = self.file_manager.create_task_dir()

        input_filename = f"input{Path(file_name).suffix if file_name else '.pdf'}"
        input_path = task_dir / input_filename
        input_path.write_bytes(file_bytes)

        self.db.create_task(
            task_id=task_id,
            task_dir=str(task_dir),
            input_filename=input_filename,
            backend=validated_backend,
            lang=validated_lang,
            formula_enable=formula_enable,
            table_enable=table_enable,
            image_analysis=image_analysis,
            start_page_id=start_page_id,
            end_page_id=end_page_id,
            server_url=effective_server_url,
            timeout_seconds=self.config.task_timeout,
        )

        task = self.db.get_task(task_id)
        created_at = task['created_at'] if task else datetime.now().isoformat()

        logger.info(f"Task {task_id} submitted to queue")

        return {
            "task_id": task_id,
            "status": "submitted",
            "created_at": created_at,
        }

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get task status and details.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            task_id: The task ID to query.

        Returns:
            Task status information dict.
        """
        task = self.db.get_task(task_id)

        if task is None:
            logger.warning(f"Task not found: {task_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
            }

        status = task['status']
        progress = task.get('progress', 0)
        message = task.get('message', f"Task is {status}")
        created_at = task['created_at']
        updated_at = task.get('updated_at') or task['created_at']

        base = {
            "task_id": task_id,
            "created_at": created_at,
        }

        if status in ('pending', 'processing'):
            return {
                **base,
                "status": status,
                "progress": progress,
                "message": message,
                "updated_at": updated_at,
            }

        if status in ('failed', 'cancelled'):
            error_msg = task.get('error') or message
            return {
                **base,
                "status": status,
                "progress": progress,
                "message": message,
                "updated_at": updated_at,
                "completed_at": updated_at,
                "error": error_msg,
            }

        if status == 'completed':
            return {
                **base,
                "status": "completed",
                "progress": progress,
                "message": message,
                "updated_at": updated_at,
                "completed_at": updated_at,
            }

        return {
            **base,
            "status": status,
            "error": f"Unknown task status: {status}",
        }

    def list_deliverables(self, task_id: str) -> dict[str, Any]:
        """List all deliverables for a completed task.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            task_id: The task ID to query.

        Returns:
            Dict with task_id, status, and artifacts list.
        """
        task = self.db.get_task(task_id)

        if task is None:
            logger.warning(f"Task not found: {task_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
                "artifacts": [],
            }

        status = task['status']
        if status != 'completed':
            return {
                "task_id": task_id,
                "status": status,
                "artifacts": [],
                "message": "Task not completed. Cannot list result artifacts.",
            }

        artifacts = self.file_manager.list_task_artifacts(
            Path(task['task_dir']),
            task['input_filename'],
            task['backend'],
        )
        return {
            "task_id": task_id,
            "status": "completed",
            "artifacts": artifacts,
        }

    def download_deliverable(
        self,
        task_id: str,
        download_key: str,
        include_content: bool = True,
    ) -> dict[str, Any]:
        """Download a specific deliverable by its download key.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            task_id: The task ID.
            download_key: The artifact download key.
            include_content: If False, returns only metadata.

        Returns:
            Dict with artifact metadata and optionally content.
        """
        task = self.db.get_task(task_id)

        if task is None:
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
            }

        status = task["status"]
        if status != "completed":
            return {
                "task_id": task_id,
                "status": status,
                "error": f"Task status is '{status}', not 'completed'",
            }

        task_dir = Path(task["task_dir"])
        self.file_manager.resolve_download_key(task_dir, download_key)
        allowed_download_keys = self.file_manager.get_allowed_download_keys(
            task_dir,
            task["input_filename"],
            task["backend"],
        )
        if download_key not in allowed_download_keys:
            return {
                "task_id": task_id,
                "status": "error",
                "error": f"Artifact '{download_key}' is not exposed by this task",
            }

        artifacts = self.file_manager.list_task_artifacts(task_dir, task["input_filename"], task["backend"])

        # Find the artifact
        artifact = None
        for item in artifacts:
            if item.get("download_key") == download_key:
                artifact = item
                break
            # Check children
            if "children" in item:
                for child in item["children"]:
                    if child.get("download_key") == download_key:
                        artifact = child
                        break
                if artifact:
                    break

        if artifact is None:
            return {
                "task_id": task_id,
                "status": "error",
                "error": "Artifact not found",
            }

        result = {
            "task_id": task_id,
            "status": "completed",
            "name": artifact["name"],
            "download_key": download_key,
            "media_type": self.file_manager.get_media_type_for_path(Path(task_dir) / download_key),
            "filename": Path(download_key).name,
            "artifact_type": artifact.get("artifact_type"),
        }

        if include_content:
            artifact_path, payload = self.file_manager.read_artifact_by_download_key(task_dir, download_key)
            result["encoding"] = "base64" if isinstance(payload, str) and artifact_path.suffix.lower() not in {".md", ".json"} else ("json" if artifact_path.suffix.lower() == ".json" else "utf-8")
            result["content"] = payload

        return result

    def get_default_deliverable(
        self,
        task_id: str,
        format: str = "markdown",
    ) -> dict[str, Any]:
        """Get the primary deliverable result or a specific logical result format.

        This is a shared implementation used by both REST and MCP protocols.
        This method provides backward-compatible default result access.

        Args:
            task_id: The task ID to query.
            format: Logical result format name. Defaults to "markdown".

        Returns:
            Dict with task_id, status, format, filename, result/payload, completed_at.
        """
        task = self.db.get_task(task_id)

        if task is None:
            logger.warning(f"Task not found: {task_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
            }

        status = task['status']
        updated_at = task.get('updated_at') or task['created_at']
        message = task.get('message', f"Task is {status}")

        if status != 'completed':
            error_msg = task.get('error') or f"Task status is '{status}', not 'completed'"
            return {
                "task_id": task_id,
                "status": status,
                "message": message,
                "updated_at": updated_at,
                "error": error_msg,
            }

        # Read the default deliverable format
        result_format, payload, filename = self.file_manager.read_task_result_format(
            Path(task['task_dir']),
            task['input_filename'],
            task['backend'],
            format,
        )

        return {
            "task_id": task_id,
            "status": "completed",
            "format": result_format,
            "filename": filename,
            "result": payload,
            "completed_at": updated_at,
        }

    def create_task_from_upload(
        self,
        upload_id: str,
        backend: Optional[str] = None,
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
    ) -> dict[str, Any]:
        """Create a task from a previously uploaded file.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            upload_id: ID of a previously uploaded file.
            backend: Parsing backend (defaults to config.default_backend).
            lang: Document language for OCR.
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            image_analysis: Enable VLM image analysis.
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).

        Returns:
            Task submission result dict with task_id, status, created_at.
        """
        effective_backend = backend if backend is not None else self.config.default_backend
        effective_server_url = server_url if server_url is not None else self.config.get_vlm_server_url()

        validated_backend = validate_backend(effective_backend)
        validated_lang = validate_language(lang)
        validate_page_range(start_page_id, end_page_id)

        upload = self.db.get_upload(upload_id)
        if upload is None:
            return {
                "task_id": "",
                "status": "error",
                "error": "Upload not found",
            }

        if upload["status"] != "uploaded":
            return {
                "task_id": "",
                "status": "error",
                "error": f"Upload status is '{upload['status']}', expected 'uploaded'",
            }

        source_path = Path(upload["file_path"])
        if not source_path.exists():
            return {
                "task_id": "",
                "status": "error",
                "error": "Uploaded file is missing",
            }

        if not self.db.consume_upload(upload_id):
            return {
                "task_id": "",
                "status": "error",
                "error": "Upload has already been consumed",
            }

        try:
            task_id, task_dir = self.file_manager.create_task_dir()
            input_filename = Path(upload["file_name"]).name
            input_path = task_dir / input_filename
            input_path.write_bytes(source_path.read_bytes())

            self.db.create_task(
                task_id=task_id,
                task_dir=str(task_dir),
                input_filename=input_filename,
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                image_analysis=image_analysis,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
                server_url=effective_server_url,
                timeout_seconds=self.config.task_timeout,
            )
        except Exception:
            self.db.release_upload(upload_id)
            raise

        task = self.db.get_task(task_id)
        created_at = task["created_at"] if task else datetime.now().isoformat()

        logger.info(f"Task {task_id} submitted from upload: {upload_id}")

        return {
            "task_id": task_id,
            "status": "submitted",
            "created_at": created_at,
        }

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel a pending or processing task.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            task_id: The task ID to cancel.

        Returns:
            Dict with cancellation status.
        """
        task = self.db.get_task(task_id)

        if task is None:
            logger.warning(f"Task not found: {task_id}")
            return {
                "task_id": task_id,
                "cancelled": False,
                "error": f"Task '{task_id}' not found",
            }

        status = task['status']

        if status in ('completed', 'failed', 'cancelled'):
            return {
                "task_id": task_id,
                "cancelled": False,
                "message": f"Task already in status '{status}'",
            }

        # Import here to avoid circular imports
        from mineru_mcp.task_queue import TaskStateService

        state = TaskStateService(self.db)
        cancelled = state.cancel(task_id, "Task cancelled by user")
        logger.info(f"Task {task_id} cancelled: {cancelled}")

        return {
            "task_id": task_id,
            "cancelled": cancelled,
            "message": "Task cancelled successfully" if cancelled else "Task could not be cancelled",
        }


# Global service instance (created lazily)
_task_service: Optional[TaskService] = None


def get_task_service() -> TaskService:
    """Get the global task service instance."""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service


def reset_task_service() -> None:
    """Reset the global task service (for testing)."""
    global _task_service
    _task_service = None