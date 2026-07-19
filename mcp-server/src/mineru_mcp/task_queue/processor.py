"""Task processor module.

Processes tasks through a dedicated MinerU worker subprocess.
"""

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.mineru_adapter import is_mineru_available, require_mineru
from mineru_mcp.postprocess import (
    PostprocessCancelledError,
    TitleLLMPostprocessor,
    build_postprocess_output_path,
    build_postprocess_summary,
)
from .database import TaskDatabase
from .file_manager import FileManager
from .state_service import TaskStateService

class TaskProcessor:
    """Task processor with Semaphore-based concurrency control.
    
    Runs local MinerU parsing through a dedicated worker subprocess.
    """
    
    def __init__(self, db: TaskDatabase, max_concurrent: int = 3):
        """Initialize task processor.
        
        Args:
            db: TaskDatabase instance.
            max_concurrent: Maximum concurrent processing tasks.
        """
        self.db = db
        self.config = get_config()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self._postprocess_cancel_flags: Dict[str, threading.Event] = {}
        logger.info(f"TaskProcessor initialized with max_concurrent={max_concurrent}")
        
    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """Callback when task is done or cancelled. Only writes terminal state
        through TaskStateService; postprocess_status is reconciled idempotently.
        """
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning(f"Task {task_id} cancelled")
            self._kill_process(task_id)
            state = TaskStateService(self.db)
            state.cancel(task_id, "Task cancelled by user or timeout")
            self._reconcile_postprocess_on_abort(task_id)
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self._kill_process(task_id)
            state = TaskStateService(self.db)
            state.fail(task_id, str(e))
            self._reconcile_postprocess_on_abort(task_id)
        finally:
            self.active_tasks.pop(task_id, None)
            self.active_processes.pop(task_id, None)
            self._postprocess_cancel_flags.pop(task_id, None)
            
    async def process_task(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """Process a task asynchronously.
        
        Args:
            task_id: Task UUID.
            task_data: Task data from database.
        """
        task = asyncio.create_task(self._process_internal(task_id, task_data))
        self.active_tasks[task_id] = task
        task.add_done_callback(lambda t: self._on_task_done(task_id, t))
        logger.info(f"Task {task_id} submitted for processing")
            
    async def _process_internal(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """Internal processing logic with Semaphore.
        
        Args:
            task_id: Task UUID.
            task_data: Task data from database.
        """
        async with self.semaphore:
            logger.info(f"Processing task {task_id}")
            
            if not is_mineru_available():
                require_mineru(task_data.get('backend', 'vlm-auto-engine'))
            
            task_dir = Path(task_data['task_dir'])
            input_file = task_dir / task_data['input_filename']
            
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")
                
            pdf_name = Path(task_data['input_filename']).stem
            
            # Note: We directly use the input file path instead of creating a temp copy.
            # The worker reads the file bytes anyway (see mineru_worker.py line 19).
            # This avoids unnecessary disk I/O (read + write + delete operations).
            
            backend = task_data.get('backend', 'vlm-auto-engine')
            lang = task_data.get('lang', 'ch')
            formula_enable = bool(task_data.get('formula_enable', 1))
            table_enable = bool(task_data.get('table_enable', 1))
            image_analysis = bool(task_data.get('image_analysis', 1))
            start_page_id = task_data.get('start_page_id', 0)
            end_page_id = task_data.get('end_page_id', 99999)
            server_url = task_data.get('server_url')
            vlm_api_key = self.config.get_vlm_api_key()
            vlm_model = self.config.get_vlm_model()
            
            self.db.add_log(task_id, "INFO", f"Started processing with backend={backend}")
            self.db.update_progress(task_id, 10, "Reading input file")
            
            try:
                worker_module = "mineru_mcp.mineru_worker"
                self.db.add_log(task_id, "INFO", f"Worker module: {worker_module}")
                config_data = {
                    "pdf_path": str(input_file),  # Use original input file directly
                    "output_dir": str(task_dir),
                    "pdf_file_names": [pdf_name],
                    "p_lang_list": [lang],
                    "backend": backend,
                    "parse_method": "auto",
                    "formula_enable": formula_enable,
                    "table_enable": table_enable,
                    "image_analysis": image_analysis,
                    "start_page_id": start_page_id,
                    "end_page_id": end_page_id if end_page_id < 99999 else None,
                    "server_url": server_url,
                    "vlm_api_key": vlm_api_key,
                    "vlm_model": vlm_model,
                }
                
                self.db.add_log(task_id, "INFO", f"Starting subprocess for backend={backend}")
                self.db.update_progress(task_id, 20, "Starting MinerU subprocess")
                
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", worker_module,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self.active_processes[task_id] = proc
                
                stdout, stderr = await proc.communicate(
                    input=json.dumps(config_data).encode()
                )
                
                returncode = proc.returncode
                self.active_processes.pop(task_id, None)
                
                self.db.update_progress(task_id, 80, "Subprocess completed, checking output")
                
                state = TaskStateService(self.db)
                
                if returncode != 0:
                    error_msg = (stderr or stdout or b"Unknown error").decode("utf-8", errors="replace")
                    logger.error(f"Worker failed: {error_msg}")
                    if bool(task_data.get("enable_postprocess", 0)):
                        # Postprocess never started; must not stay 'pending'
                        self._set_postprocess_status(task_id, "skipped")
                    state.fail(task_id, error_msg[:500])
                    self.db.add_log(task_id, "ERROR", f"Worker error: {error_msg[:500]}")
                    return
                
                file_manager = FileManager(output_root=str(self.db.db_path.parent))
                output_files = file_manager.get_output_files(task_dir, task_data['input_filename'], backend)
                validation = file_manager.validate_task_outputs(task_dir, task_data['input_filename'], backend)

                if validation['required_missing']:
                    missing_outputs = ", ".join(validation['required_missing'])
                    logger.warning(f"Required outputs missing for task {task_id}: {missing_outputs}")
                    if bool(task_data.get("enable_postprocess", 0)):
                        # Postprocess never started; must not stay 'pending'
                        self._set_postprocess_status(task_id, "skipped")
                    state.fail(task_id, f"Required outputs missing: {missing_outputs}")
                    self.db.add_log(task_id, "ERROR", f"Required outputs missing: {missing_outputs}")
                    return

                if validation['recommended_missing']:
                    missing_outputs = ", ".join(validation['recommended_missing'])
                    self.db.add_log(task_id, "WARNING", f"Recommended outputs missing: {missing_outputs}")

                if validation['optional_missing']:
                    missing_outputs = ", ".join(validation['optional_missing'])
                    self.db.add_log(task_id, "INFO", f"Optional outputs missing: {missing_outputs}")

                if bool(task_data.get("enable_postprocess", 0)):
                    self._set_postprocess_status(task_id, "processing")
                    self.db.update_progress(task_id, 90, "Running postprocess")
                    cancel_flag = threading.Event()
                    self._postprocess_cancel_flags[task_id] = cancel_flag
                    try:
                        await asyncio.to_thread(
                            self._run_postprocess, task_id, task_data, output_files["md"], cancel_flag
                        )
                    finally:
                        self._postprocess_cancel_flags.pop(task_id, None)
                # When postprocess is not enabled the creation-time "not_enabled" value
                # is already correct; there is no need for a redundant UPDATE here.
                
                state.complete(task_id)
                self.db.add_log(task_id, "INFO", f"Processing completed. Output: {output_files['md']}")
                logger.info(f"Task {task_id} completed successfully. Output: {output_files['md']}")

            except PostprocessCancelledError:
                # Thread detected the cancel flag before the CancelledError
                # reached the coroutine.  Convert to CancelledError so
                # _on_task_done routes through the cancellation path.
                raise asyncio.CancelledError("Task cancelled during postprocess")
                    
            except Exception as e:
                postprocess_failed = False
                if bool(task_data.get("enable_postprocess", 0)):
                    try:
                        current_status = (self.db.get_task(task_id) or {}).get("postprocess_status")
                        if current_status == "processing":
                            postprocess_failed = True
                            self._set_postprocess_status(task_id, "failed")
                        elif current_status == "pending":
                            self._set_postprocess_status(task_id, "skipped")
                        # Terminal values (completed, failed, skipped) are left
                        # untouched — a successful postprocess whose state.complete()
                        # raised must not be downgraded.
                    except Exception:
                        pass
                stage = "Postprocess" if postprocess_failed else "Processing"
                self.db.add_log(task_id, "ERROR", f"{stage} error: {str(e)}")
                raise
                
    def _kill_process(self, task_id: str):
        """Kill the subprocess associated with a task.
        
        Args:
            task_id: Task UUID.
        """
        proc = self.active_processes.pop(task_id, None)
        if proc and proc.returncode is None:
            try:
                proc.kill()
                logger.info(f"Killed subprocess for task {task_id}")
            except Exception as e:
                logger.warning(f"Failed to kill subprocess for task {task_id}: {e}")

    def _set_postprocess_status(
        self,
        task_id: str,
        status: str,
        result_summary: str | None = None,
        expect_status: str | None = None,
    ) -> int:
        """Update the postprocess stage status — the single write authority.

        Status enum: not_enabled / pending / processing / completed / failed / skipped.
        When expect_status is set, the UPDATE is conditional (optimistic guard
        against late writes on tasks that have already reached a terminal state).
        Returns the affected row count.
        """
        if result_summary is not None:
            sql = "UPDATE tasks SET result_summary = ?, postprocess_status = ?, updated_at = ? WHERE task_id = ?"
            params: list = [result_summary, status, datetime.now().isoformat(), task_id]
        else:
            sql = "UPDATE tasks SET postprocess_status = ?, updated_at = ? WHERE task_id = ?"
            params = [status, datetime.now().isoformat(), task_id]
        if expect_status is not None:
            sql += " AND postprocess_status = ?"
            params.append(expect_status)
        return self.db.execute(sql, tuple(params))

    def _reconcile_postprocess_on_abort(self, task_id: str) -> None:
        """Bring postprocess_status to a terminal value after cancel/fail.

        The task's main status is owned by TaskStateService; this only reconciles
        the postprocess stage: pending→skipped (never started), processing→failed
        (was executing). Terminal values are left untouched (idempotent).
        """
        try:
            task = self.db.get_task(task_id) or {}
            if not task.get("enable_postprocess"):
                return
            current = task.get("postprocess_status")
            if current == "pending":
                self._set_postprocess_status(task_id, "skipped")
            elif current == "processing":
                self._set_postprocess_status(task_id, "failed")
        except Exception:
            logger.warning(f"Failed to reconcile postprocess status for task {task_id}")

    def _run_postprocess(
        self,
        task_id: str,
        task_data: Dict[str, Any],
        md_path: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        rule_id = task_data.get("postprocess_rule_id")
        if not rule_id:
            raise RuntimeError("Postprocess enabled but postprocess_rule_id is missing")

        prompt_snapshot = task_data.get("postprocess_prompt_snapshot")
        title_snapshot = task_data.get("postprocess_rule_title_snapshot") or rule_id
        if not prompt_snapshot:
            raise RuntimeError(f"Postprocess prompt snapshot missing for rule '{rule_id}'")

        markdown_text = md_path.read_text(encoding="utf-8")
        postprocessor = TitleLLMPostprocessor(self.config)
        processed_text, metadata = postprocessor.process_markdown(
            markdown_text=markdown_text,
            prompt=prompt_snapshot,
            context_size=task_data.get("postprocess_context_size"),
            cancel_event=cancel_event,
        )

        # Write the artifact file first — if this fails the exception
        # propagates and the task fails without a bogus completed state.
        output_path = build_postprocess_output_path(md_path, task_data.get("postprocess_output_filename"))
        output_path.write_text(
            processed_text + ("\n" if processed_text and not processed_text.endswith("\n") else ""),
            encoding="utf-8",
        )

        summary = build_postprocess_summary(title_snapshot, metadata)
        # Guarded completion: only transition postprocess_status to completed
        # when the task is still genuinely in the processing stage.
        updated = self._set_postprocess_status(
            task_id, "completed", result_summary=summary, expect_status="processing"
        )
        if not updated:
            self.db.add_log(
                task_id, "WARNING",
                "Postprocess result discarded: task no longer in postprocess-processing state",
            )
            return

        self.db.add_log(
            task_id, "INFO",
            f"Postprocess completed with rule={title_snapshot} chunks={metadata.get('chunks', 1)}",
        )

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.
        
        Args:
            task_id: Task UUID.
            
        Returns:
            True if task was cancelled, False if not found or already done.
        """
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            flag = self._postprocess_cancel_flags.get(task_id)
            if flag is not None:
                flag.set()
            self._kill_process(task_id)
            task.cancel()
            logger.info(f"Task {task_id} cancelled")
            return True
        return False
        
    def get_active_count(self) -> int:
        """Get count of active (processing) tasks.
        
        Returns:
            Number of active tasks.
        """
        return len([t for t in self.active_tasks.values() if not t.done()])
        
    def get_active_task_ids(self) -> list:
        """Get list of active task IDs.
        
        Returns:
            List of active task IDs.
        """
        return [tid for tid, task in self.active_tasks.items() if not task.done()]
