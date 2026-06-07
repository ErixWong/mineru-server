"""Task processor module.

Processes tasks through a dedicated MinerU worker subprocess.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from loguru import logger

from mineru_mcp.mineru_adapter import is_mineru_available, read_file_bytes
from .database import TaskDatabase
from .file_manager import FileManager
from .state_service import TaskStateService

DEFAULT_TIMEOUT = 1800


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
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.active_processes: Dict[str, subprocess.Popen] = {}
        logger.info(f"TaskProcessor initialized with max_concurrent={max_concurrent}")
        
    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """Callback when task is done."""
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
            state = TaskStateService(self.db)
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
                raise RuntimeError("MinerU dependency is unavailable. Cannot process tasks.")
            
            task_dir = Path(task_data['task_dir'])
            input_file = task_dir / task_data['input_filename']
            
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")
                
            pdf_name = Path(task_data['input_filename']).stem
            pdf_bytes = await asyncio.to_thread(read_file_bytes, input_file)
            
            backend = task_data.get('backend', 'vlm-auto-engine')
            lang = task_data.get('lang', 'ch')
            formula_enable = bool(task_data.get('formula_enable', 1))
            table_enable = bool(task_data.get('table_enable', 1))
            image_analysis = bool(task_data.get('image_analysis', 1))
            start_page_id = task_data.get('start_page_id', 0)
            end_page_id = task_data.get('end_page_id', 99999)
            server_url = task_data.get('server_url')
            
            self.db.add_log(task_id, "INFO", f"Started processing with backend={backend}")
            self.db.update_progress(task_id, 10, "Reading input file")
            
            try:
                self.db.add_log(task_id, "INFO", "Preparing subprocess...")
                
                temp_pdf = Path(task_dir) / "_temp_input.pdf"
                temp_pdf.write_bytes(pdf_bytes)
                self.db.add_log(task_id, "INFO", f"Temp PDF created: {temp_pdf}")
                self.db.update_progress(task_id, 20, "Prepared input file")
                
                worker_module = "mineru_mcp.mineru_worker"
                self.db.add_log(task_id, "INFO", f"Worker module: {worker_module}")
                config_data = {
                    "pdf_path": str(temp_pdf),
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
                }
                
                self.db.add_log(task_id, "INFO", f"Starting subprocess for backend={backend}")
                self.db.update_progress(task_id, 30, "Starting MinerU subprocess")
                
                try:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", worker_module,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    self.active_processes[task_id] = proc
                    
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(input=json.dumps(config_data).encode()),
                        timeout=DEFAULT_TIMEOUT,
                    )
                    
                    returncode = proc.returncode
                    self.active_processes.pop(task_id, None)
                    
                    self.db.update_progress(task_id, 80, "Subprocess completed, checking output")
                    
                    state = TaskStateService(self.db)
                    
                    if returncode != 0:
                        error_msg = (stderr or stdout or b"Unknown error").decode("utf-8", errors="replace")
                        logger.error(f"Worker failed: {error_msg}")
                        state.fail(task_id, error_msg[:500])
                        self.db.add_log(task_id, "ERROR", f"Worker error: {error_msg[:500]}")
                        return
                    
                    file_manager = FileManager(output_root=str(self.db.db_path.parent))
                    output_files = file_manager.get_output_files(task_dir, task_data['input_filename'], backend)
                    md_path = output_files['md']
                    
                    if not md_path.exists():
                        logger.warning(f"Output markdown not found: {md_path}")
                        state.fail(task_id, "Output file not generated")
                        self.db.add_log(task_id, "ERROR", f"Expected output not found: {md_path}")
                        return
                    
                    state.complete(task_id)
                    self.db.add_log(task_id, "INFO", f"Processing completed. Output: {md_path}")
                    logger.info(f"Task {task_id} completed successfully. Output: {md_path}")
                    
                finally:
                    if temp_pdf.exists():
                        temp_pdf.unlink()
                        
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
