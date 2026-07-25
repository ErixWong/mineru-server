"""
Task Service Layer

Provides shared business logic for task operations that can be used
by both REST API (api.py) and MCP Protocol (server.py).

This is the first step in extracting shared service layer from duplicated
implementations across protocols.
"""

import base64
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mineru_mcp.config import get_config, MCPConfig
from mineru_mcp.models import TaskStatus
from mineru_mcp.postprocess import (
    TitleLLMPostprocessor,
    normalize_context_size,
)
from mineru_mcp.principal import CurrentPrincipal, PrincipalType
from mineru_mcp.task_queue import TaskDatabase, FileManager
from mineru_mcp.task_queue.file_manager import clean_display_name, stored_filename, resolve_stored_filename
from mineru_mcp.task_queue.postprocess_runner import build_plan_steps_snapshot
from mineru_mcp.validation import (
    validate_language,
    validate_page_range,
    resolve_backend_options,
    ValidationError,
    MAX_FILE_SIZE,
    ERROR_FILE_TOO_LARGE,
)


def serialize_postprocess_run(run: dict) -> dict:
    """将 run 记录序列化为对外响应结构。

    steps 字段合并快照与执行结果：已执行的步骤带真实状态，
    未执行的步骤回退为 pending。
    """
    steps_snapshot = run.get("steps_snapshot") or []
    step_results = run.get("step_results") or []
    steps: list[dict] = []
    for index, snapshot in enumerate(steps_snapshot):
        result = step_results[index] if index < len(step_results) else {}
        steps.append({
            "action_id": snapshot.get("action_id"),
            "name": snapshot.get("name"),
            "output_filename": snapshot.get("output_filename"),
            "status": result.get("status") or "pending",
            "chunks": result.get("chunks", 0),
            "error": result.get("error"),
        })
    return {
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "plan_id": run.get("plan_id"),
        "plan_title": run.get("plan_title_snapshot"),
        "status": run.get("status"),
        "current_step": run.get("current_step", 0),
        "trigger_source": run.get("trigger_source"),
        "steps": steps,
        "error": run.get("error"),
        "created_at": run.get("created_at"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
    }


def collect_postprocess_filenames(db: TaskDatabase, task: dict) -> list[str]:
    """聚合任务全部后处理 run 步骤的产物文件名（去重、保持顺序）。

    兼容历史任务：迁移前的任务没有 run 记录，但 tasks.postprocess_output_filename
    列仍冻结着旧产物文件名，一并纳入以保证旧交付物可见。
    """
    names: list[str] = []
    try:
        runs = db.list_postprocess_runs(task_id=task["task_id"])
        for run in runs:
            for step in run.get("steps_snapshot") or []:
                filename = step.get("output_filename")
                if filename and filename not in names:
                    names.append(filename)
    except Exception:
        logger.warning(f"Failed to collect postprocess runs for task {task['task_id']}")
    legacy_filename = task.get("postprocess_output_filename")
    if legacy_filename and legacy_filename not in names:
        names.append(legacy_filename)
    return names


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
        lang: Optional[str] = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        server_url: Optional[str] = None,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        enable_postprocess: Optional[bool] = None,
        postprocess_rule_id: Optional[str] = None,
        postprocess_context_size: Optional[int] = None,
        principal: CurrentPrincipal = None,
    ) -> dict[str, Any]:
        """Create a task from base64-encoded file content.

        This is a shared implementation used by both REST and MCP protocols.

        Args:
            file_base64: Base64-encoded PDF file content.
            file_name: Optional file name for display and extension detection.
            backend: Parsing backend (defaults to config.default_backend).
            lang: Document language for OCR. Empty/None falls back to the default (ch).
            formula_enable: Enable mathematical formula recognition.
            table_enable: Enable table structure recognition.
            image_analysis: Enable VLM image analysis.
            server_url: VLM server URL for http-client backends.
            start_page_id: Starting page number (0-indexed).
            end_page_id: Ending page number (0-indexed).
            enable_postprocess: Whether to run postprocess after parsing. None means inherit caller default.
            postprocess_rule_id: Selected postprocess rule ID.
            postprocess_context_size: Context window size for postprocess.
            principal: The current principal (for ownership). Required for authenticated callers.

        Returns:
            Task submission result dict with task_id, status, created_at.
            
        Note:
            HTTP caller flows must provide a resolved principal.
            Local stdio-style flows may pass a stdio principal explicitly.
        """
        if principal is None:
            raise ValueError("principal is required")
        
        effective_backend = backend if backend is not None else self.config.default_backend

        validated_backend, effective_server_url = resolve_backend_options(
            effective_backend,
            server_url,
            self.config.get_vlm_server_url(),
        )
        # Empty/None lang means "no preference" and falls back to the default (ch).
        validated_lang = validate_language(lang or "ch")
        validate_page_range(start_page_id, end_page_id)
        input_filename = clean_display_name(file_name) if file_name else "input.pdf"

        effective_postprocess_rule_id = postprocess_rule_id
        effective_enable_postprocess = enable_postprocess
        caller_id = getattr(principal, 'caller_id', None)
        if effective_enable_postprocess is None and not effective_postprocess_rule_id and caller_id:
            caller = self.db.get_caller(caller_id)
            default_rule_id = caller.get("default_postprocess_rule_id") if caller else None
            if default_rule_id:
                effective_postprocess_rule_id = default_rule_id
                effective_enable_postprocess = True
            else:
                effective_enable_postprocess = False
        elif effective_enable_postprocess is None:
            effective_enable_postprocess = bool(effective_postprocess_rule_id)

        if effective_enable_postprocess is False:
            effective_postprocess_rule_id = None

        normalized_postprocess_context_size = None

        logger.info(f"Decoding base64 file: {file_name or 'unnamed'}")

        file_bytes = base64.b64decode(file_base64)

        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValidationError(
                ERROR_FILE_TOO_LARGE,
                f"File size ({len(file_bytes)} bytes) exceeds maximum ({MAX_FILE_SIZE} bytes)",
                {"size": len(file_bytes), "max_size": MAX_FILE_SIZE},
            )

        # Create the task directory first — postprocess setup needs task_id[:8]
        task_id, task_dir = self.file_manager.create_task_dir()
        stored_name = stored_filename(task_id, input_filename)

        try:
            if effective_enable_postprocess:
                postprocessor = TitleLLMPostprocessor(self.config)
                if not postprocessor.is_configured():
                    raise ValidationError(
                        "POSTPROCESS_LLM_NOT_CONFIGURED",
                        postprocessor.get_config_error_message(),
                    )
                if not effective_postprocess_rule_id:
                    raise ValidationError(
                        "INVALID_POSTPROCESS_PLAN",
                        "postprocess_rule_id (plan) is required when enable_postprocess is true",
                    )
                normalized_postprocess_context_size = normalize_context_size(
                    postprocess_context_size,
                    self.config.postprocess_context_size,
                )
                # 解析 plan 步骤快照做 fail-fast 校验；真正的快照冻结发生在 run 创建时。
                try:
                    steps_snapshot = build_plan_steps_snapshot(
                        self.db,
                        effective_postprocess_rule_id,
                        default_context_size=normalized_postprocess_context_size,
                    )
                except ValueError as exc:
                    raise ValidationError("INVALID_POSTPROCESS_PLAN", str(exc)) from exc
                source_markdown_filename = self.file_manager.get_output_files(
                    task_dir,
                    stored_name,
                    validated_backend,
                )["md"].name
                for step in steps_snapshot:
                    if step["output_filename"] == source_markdown_filename:
                        raise ValidationError(
                            "INVALID_POSTPROCESS_OUTPUT_FILENAME",
                            f"postprocess output filename '{step['output_filename']}' must differ from the source markdown filename",
                        )

            # Write input file using the derived storage name
            input_path = task_dir / stored_name
            input_path.write_bytes(file_bytes)
        except Exception:
            shutil.rmtree(task_dir, ignore_errors=True)
            raise

        # postprocess_rule_id 列承载 plan_id；步骤快照在 run 创建时冻结到 postprocess_runs 表。
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
            owner_id=principal.principal_id,
            owner_type=principal.principal_type.value,
            caller_id=caller_id,  # Write caller_id if available
            enable_postprocess=effective_enable_postprocess,
            postprocess_rule_id=effective_postprocess_rule_id,
            postprocess_context_size=normalized_postprocess_context_size,
            postprocess_status="pending" if effective_enable_postprocess else "not_enabled",
        )

        task = self.db.get_task(task_id)
        created_at = task['created_at'] if task else datetime.now().isoformat()

        logger.info(f"Task {task_id} submitted to queue (owner={principal.principal_id})")

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

    def _collect_postprocess_filenames(self, task: dict) -> list[str]:
        return collect_postprocess_filenames(self.db, task)

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
            resolve_stored_filename(task_id, task['input_filename'], Path(task['task_dir'])),
            task['backend'],
            self._collect_postprocess_filenames(task),
            display_name=task['input_filename'],
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
        task_id = task["task_id"]
        stored_name = resolve_stored_filename(task_id, task["input_filename"], task_dir)
        try:
            self.file_manager.resolve_download_key(task_dir, download_key)
        except ValueError:
            return {
                "task_id": task_id,
                "status": "error",
                "error_code": "INVALID_DOWNLOAD_KEY",
                "error": "Invalid download key",
            }
        allowed_download_keys = self.file_manager.get_allowed_download_keys(
            task_dir,
            stored_name,
            task["backend"],
            self._collect_postprocess_filenames(task),
        )
        if download_key not in allowed_download_keys:
            return {
                "task_id": task_id,
                "status": "error",
                "error_code": "ARTIFACT_NOT_AVAILABLE",
                "error": f"Artifact '{download_key}' is not exposed by this task",
            }

        artifacts = self.file_manager.list_task_artifacts(
            task_dir,
            stored_name,
            task["backend"],
            self._collect_postprocess_filenames(task),
            display_name=task["input_filename"],
        )

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

    # ==================== Authorization Methods ====================
    
    def _check_task_ownership(
        self,
        task_id: str,
        principal: CurrentPrincipal,
    ) -> bool:
        """Check if the principal owns the task.
        
        Args:
            task_id: The task ID to check.
            principal: The current principal.
            
        Returns:
            True if the principal owns the task or is admin.
        """
        # Admin can access any task
        if principal.is_admin():
            return True
        
        # Single user mode: allow all
        if principal.is_single_user_mode():
            return True
        
        task = self.db.get_task(task_id)
        if task is None:
            return False
        
        return task.get("owner_id") == principal.principal_id
    
    def _get_owner_filter_sql(self, principal: CurrentPrincipal) -> tuple[str, tuple]:
        """Get SQL filter for owner-based queries.
        
        Args:
            principal: The current principal.
            
        Returns:
            Tuple of (WHERE clause, params).
        """
        if principal.is_admin():
            # Admin sees all tasks
            return ("", ())
        elif principal.is_single_user_mode():
            # Single user mode: no filter
            return ("", ())
        else:
            # Filter by owner_id
            return ("WHERE owner_id = ?", (principal.principal_id,))
    
    def get_tasks_for_principal(
        self,
        principal: CurrentPrincipal,
        status: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get tasks visible to the principal.
        
        Args:
            principal: The current principal.
            status: Optional status filter.
            limit: Maximum number of tasks to return.
            
        Returns:
            List of task dicts visible to the principal.
        """
        if principal.is_admin():
            # Admin sees all tasks
            if status:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (status, limit))
            else:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (limit,))
        elif principal.is_single_user_mode():
            # Single user mode: no filter
            if status:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (status, limit))
            else:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (limit,))
        else:
            # Filter by owner_id
            if status:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks WHERE owner_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (principal.principal_id, status, limit))
            else:
                sql = """SELECT task_id, input_filename as filename, status, progress, message, created_at, updated_at 
                         FROM tasks WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?"""
                return self.db.fetch_all(sql, (principal.principal_id, limit))
    
    def get_task_status_authorized(
        self,
        task_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """Get task status with authorization check.
        
        Args:
            task_id: The task ID to query.
            principal: The current principal.
            
        Returns:
            Task status dict, or not_found if not authorized.
        """
        # Check ownership
        if not self._check_task_ownership(task_id, principal):
            logger.warning(f"Unauthorized access attempt to task {task_id} by principal {principal.principal_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
            }
        
        return self.get_task_status(task_id)
    
    def list_deliverables_authorized(
        self,
        task_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """List deliverables with authorization check.
        
        Args:
            task_id: The task ID to query.
            principal: The current principal.
            
        Returns:
            Deliverables dict, or not_found if not authorized.
        """
        # Check ownership
        if not self._check_task_ownership(task_id, principal):
            logger.warning(f"Unauthorized deliverables access to task {task_id} by principal {principal.principal_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
                "artifacts": [],
            }
        
        return self.list_deliverables(task_id)
    
    def download_deliverable_authorized(
        self,
        task_id: str,
        download_key: str,
        include_content: bool = True,
        principal: CurrentPrincipal = None,
    ) -> dict[str, Any]:
        """Download deliverable with authorization check.
        
        Args:
            task_id: The task ID.
            download_key: The artifact download key.
            include_content: If False, returns only metadata.
            principal: The current principal.
            
        Returns:
            Deliverable dict, or not_found if not authorized.
        """
        # Check ownership
        if not self._check_task_ownership(task_id, principal):
            logger.warning(f"Unauthorized download access to task {task_id} by principal {principal.principal_id}")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": f"Task '{task_id}' not found",
            }
        
        return self.download_deliverable(task_id, download_key, include_content)
    
    def cancel_task_authorized(
        self,
        task_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """Cancel task with authorization check.

        Args:
            task_id: The task ID to cancel.
            principal: The current principal.

        Returns:
            Cancellation result dict, or not_found if not authorized.
        """
        # Check ownership
        if not self._check_task_ownership(task_id, principal):
            logger.warning(f"Unauthorized cancel attempt on task {task_id} by principal {principal.principal_id}")
            return {
                "task_id": task_id,
                "cancelled": False,
                "error": f"Task '{task_id}' not found",
            }

        return self.cancel_task(task_id)

    # ==================== Postprocess Runs ====================

    def _get_postprocess_runner(self):
        """取进程内 runner（生产路径）；未装配时退回临时实例（测试/工具场景）。

        create_run 与 pending 取消是纯 DB 操作，临时实例即可胜任；
        running 取消的进程内信号只有生产 runner 持有。
        """
        from mineru_mcp.app import get_postprocess_runner
        runner = get_postprocess_runner()
        if runner is not None:
            return runner
        from mineru_mcp.task_queue import PostprocessRunner
        return PostprocessRunner(db=self.db, config=self.config)

    def list_enabled_postprocess_plans(self) -> list[dict[str, Any]]:
        """列出可用的后处理方案（供调用方选择 plan_id）。"""
        plans = self.db.list_postprocess_plans(include_disabled=False)
        items = []
        for plan in plans:
            steps = []
            for step in plan.get("steps") or []:
                action = self.db.get_postprocess_action(step.get("action_id")) if step.get("action_id") else None
                if not action:
                    continue
                config = action.get("config") or {}
                steps.append({
                    "action_id": action["action_id"],
                    "name": action["name"],
                    "output_filename": step.get("output_filename") or config.get("output_filename"),
                })
            items.append({
                "plan_id": plan["plan_id"],
                "title": plan["title"],
                "description": plan.get("description"),
                "steps": steps,
            })
        return items

    def run_postprocess_authorized(
        self,
        task_id: str,
        plan_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """手动触发后处理 run（带 owner 校验）。"""
        if not self._check_task_ownership(task_id, principal):
            logger.warning(f"Unauthorized postprocess trigger on task {task_id} by principal {principal.principal_id}")
            return {"task_id": task_id, "status": "not_found", "error": f"Task '{task_id}' not found"}

        task = self.db.get_task(task_id)
        if task["status"] != "completed":
            return {
                "task_id": task_id,
                "status": "error",
                "error": f"Task status is '{task['status']}', postprocess requires 'completed'",
            }
        postprocessor = TitleLLMPostprocessor(self.config)
        if not postprocessor.is_configured():
            return {
                "task_id": task_id,
                "status": "error",
                "error": postprocessor.get_config_error_message(),
            }

        try:
            run_id = self._get_postprocess_runner().create_run(task_id, plan_id, trigger_source="manual")
        except ValueError as e:
            return {"task_id": task_id, "status": "error", "error": str(e)}

        run = self.db.get_postprocess_run(run_id)
        return {"task_id": task_id, "status": "ok", "run": serialize_postprocess_run(run)}

    def list_postprocess_runs_authorized(
        self,
        task_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """查询任务的后处理 run 列表（带 owner 校验）。"""
        if not self._check_task_ownership(task_id, principal):
            return {"task_id": task_id, "status": "not_found", "error": f"Task '{task_id}' not found", "runs": []}

        runs = self.db.list_postprocess_runs(task_id=task_id)
        # 对外展示按创建时间倒序（最新在前）
        runs = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
        return {
            "task_id": task_id,
            "status": "ok",
            "runs": [serialize_postprocess_run(run) for run in runs],
        }

    def cancel_postprocess_run_authorized(
        self,
        run_id: str,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        """取消后处理 run（带任务 owner 校验）。"""
        run = self.db.get_postprocess_run(run_id)
        if not run or not self._check_task_ownership(run["task_id"], principal):
            return {"run_id": run_id, "status": "not_found", "error": f"Run '{run_id}' not found"}

        cancelled = self._get_postprocess_runner().cancel_run(run_id)
        current = self.db.get_postprocess_run(run_id)
        return {
            "run_id": run_id,
            "status": "ok" if cancelled else "error",
            "cancelled": cancelled,
            "run": serialize_postprocess_run(current) if current else None,
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
