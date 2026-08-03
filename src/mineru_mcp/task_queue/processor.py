"""Task processor module.

Processes tasks through a dedicated MinerU worker subprocess.

后处理与解析完全解耦：解析完成即任务完成；启用后处理的任务在解析产出
验证通过后创建一个 auto run 交给 PostprocessRunner 异步执行。
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.mineru_adapter import is_mineru_available, require_mineru
from .database import TaskDatabase
from .file_manager import FileManager
from .file_manager import resolve_stored_filename
from .state_service import TaskStateService

class TaskProcessor:
    """Task processor with Semaphore-based concurrency control.

    Runs local MinerU parsing through a dedicated worker subprocess.
    """

    def __init__(self, db: TaskDatabase, max_concurrent: int = 3, postprocess_runner=None):
        """Initialize task processor.

        Args:
            db: TaskDatabase instance.
            max_concurrent: Maximum concurrent processing tasks.
            postprocess_runner: Optional PostprocessRunner for auto postprocess runs.
        """
        self.db = db
        self.config = get_config()
        self.postprocess_runner = postprocess_runner
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.active_processes: Dict[str, subprocess.Popen] = {}
        logger.info(f"TaskProcessor initialized with max_concurrent={max_concurrent}")

    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """Callback when task is done or cancelled. Only writes terminal state
        through TaskStateService.
        """
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning(f"Task {task_id} cancelled")
            self._kill_process(task_id)
            state = TaskStateService(self.db)
            state.cancel(task_id, "Task cancelled by user or timeout")
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self._kill_process(task_id)
            state = TaskStateService(self.db, retry_limit=self.config.retry_limit)
            state.fail(task_id, str(e))
        finally:
            self.active_tasks.pop(task_id, None)
            self.active_processes.pop(task_id, None)
            
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
            task_id = task_data['task_id']
            stored_name = resolve_stored_filename(task_id, task_data['input_filename'], task_dir)
            input_file = task_dir / stored_name
            
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")
                
            pdf_name = Path(stored_name).stem
            
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
            vlm_max_concurrency = self.config.vlm_max_concurrency
            
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
                    "max_concurrency": vlm_max_concurrency,
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
                
                state = TaskStateService(self.db, retry_limit=self.config.retry_limit)
                
                if returncode != 0:
                    error_msg = (stderr or stdout or b"Unknown error").decode("utf-8", errors="replace")
                    logger.error(f"Worker failed: {error_msg}")
                    # 解析失败时不创建 auto run，后处理状态由 run 表独立承载
                    state.fail(task_id, error_msg[:500])
                    self.db.add_log(task_id, "ERROR", f"Worker error: {error_msg[:500]}")
                    return
                
                file_manager = FileManager(output_root=str(self.db.db_path.parent))
                output_files = file_manager.get_output_files(task_dir, stored_name, backend)
                validation = file_manager.validate_task_outputs(task_dir, stored_name, backend)

                if validation['required_missing']:
                    missing_outputs = ", ".join(validation['required_missing'])
                    logger.warning(f"Required outputs missing for task {task_id}: {missing_outputs}")
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
                    self.queue_auto_postprocess(task_id, task_data)

                # 解析完成即任务完成；后处理 run 拥有独立生命周期
                state.complete(task_id)
                self.db.add_log(task_id, "INFO", f"Processing completed. Output: {output_files['md']}")
                logger.info(f"Task {task_id} completed successfully. Output: {output_files['md']}")

            except Exception as e:
                self.db.add_log(task_id, "ERROR", f"Processing error: {str(e)}")
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

    def queue_auto_postprocess(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """解析成功后为任务创建 auto 后处理 run（异步执行，不阻塞任务完成）。

        供 processor 正常完成路径与 scheduler 去重完成路径共用。
        """
        if self.postprocess_runner is None:
            self.db.add_log(task_id, "WARNING", "Postprocess enabled but runner is not configured; skipping")
            return
        plan_id = task_data.get("postprocess_rule_id")
        if not plan_id:
            self.db.add_log(task_id, "WARNING", "Postprocess enabled but no plan bound; skipping")
            return
        try:
            run_id = self.postprocess_runner.create_run(
                task_id,
                plan_id,
                trigger_source="auto",
                default_context_size=task_data.get("postprocess_context_size"),
            )
            self.db.add_log(task_id, "INFO", f"Postprocess run {run_id} queued (auto, plan={plan_id})")
        except Exception as e:
            # run 创建失败不影响解析任务本身的完成状态
            logger.error(f"Failed to queue auto postprocess run for task {task_id}: {e}")
            self.db.add_log(task_id, "ERROR", f"Failed to queue postprocess run: {str(e)[:300]}")

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.

        Args:
            task_id: Task UUID.

        Returns:
            True if task was cancelled, False if not found or already done.
        """
        task = self.active_tasks.get(task_id)
        if task and not task.done():
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
