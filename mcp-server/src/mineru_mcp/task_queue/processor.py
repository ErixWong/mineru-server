"""Task Processor Module

Processes tasks by directly calling MinerU core functions (aio_do_parse).
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from loguru import logger

try:
    from mineru.cli.common import do_parse, read_fn
    MINERU_AVAILABLE = True
    logger.info("MinerU core functions imported successfully")
except ImportError as e:
    MINERU_AVAILABLE = False
    logger.warning(f"MinerU not available: {e}. Using mock implementation.")
    
    def do_parse(*args, **kwargs):
        raise NotImplementedError("MinerU not installed")
        
    def read_fn(path: Path) -> bytes:
        raise NotImplementedError("MinerU not installed")

from .database import TaskDatabase


class TaskProcessor:
    """Task processor with Semaphore-based concurrency control.
    
    Directly calls MinerU core functions instead of HTTP API.
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
        logger.info(f"TaskProcessor initialized with max_concurrent={max_concurrent}")
        
    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """Callback when task is done.
        
        Args:
            task_id: Task UUID.
            task: Completed asyncio.Task.
        """
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning(f"Task {task_id} cancelled")
            self.db.update_status(task_id, "cancelled", error="Task cancelled by user or timeout")
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.db.update_status(task_id, "failed", error=str(e))
        finally:
            self.active_tasks.pop(task_id, None)
            
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
            
            if not MINERU_AVAILABLE:
                raise NotImplementedError("MinerU not installed. Cannot process tasks.")
                
            task_dir = Path(task_data['task_dir'])
            input_file = task_dir / task_data['input_filename']
            
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")
                
            pdf_name = Path(task_data['input_filename']).stem
            pdf_bytes = await asyncio.to_thread(read_fn, input_file)
            
            backend = task_data.get('backend', 'vlm-auto-engine')
            lang = task_data.get('lang', 'ch')
            formula_enable = bool(task_data.get('formula_enable', 1))
            table_enable = bool(task_data.get('table_enable', 1))
            image_analysis = bool(task_data.get('image_analysis', 1))
            start_page_id = task_data.get('start_page_id', 0)
            end_page_id = task_data.get('end_page_id', 99999)
            server_url = task_data.get('server_url')
            
            self.db.add_log(task_id, "INFO", f"Started processing with backend={backend}")
            
            try:
                import subprocess
                import json
                from pathlib import Path as PathLib
                
                self.db.add_log(task_id, "INFO", "Preparing subprocess...")
                
                # Write PDF bytes to temp file (do_parse needs file path for multiprocessing)
                temp_pdf = PathLib(task_dir) / "_temp_input.pdf"
                temp_pdf.write_bytes(pdf_bytes)
                self.db.add_log(task_id, "INFO", f"Temp PDF created: {temp_pdf}")
                
                # Prepare config for worker script
                worker_script = PathLib(__file__).parent.parent / "mineru_worker.py"
                self.db.add_log(task_id, "INFO", f"Worker script: {worker_script}")
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
                
                # Run worker script in subprocess
                self.db.add_log(task_id, "INFO", f"Starting subprocess for backend={backend}")
                
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, str(worker_script)],
                    input=json.dumps(config_data),
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                
                # Clean up temp file
                if temp_pdf.exists():
                    temp_pdf.unlink()
                
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout or "Unknown error"
                    logger.error(f"Worker failed: {error_msg}")
                    self.db.update_status(task_id, "failed", error=error_msg[:500])
                    self.db.add_log(task_id, "ERROR", f"Worker error: {error_msg[:500]}")
                    return
                
                # Verify output file exists before marking completed
                from .file_manager import FileManager
                file_manager = FileManager()
                output_files = file_manager.get_output_files(task_dir, task_data['input_filename'], backend)
                md_path = output_files['md']
                
                if not md_path.exists():
                    logger.warning(f"Output markdown not found: {md_path}")
                    self.db.update_status(task_id, "failed", error="Output file not generated")
                    self.db.add_log(task_id, "ERROR", f"Expected output not found: {md_path}")
                    return
                
                self.db.update_status(task_id, "completed")
                self.db.add_log(task_id, "INFO", f"Processing completed. Output: {md_path}")
                logger.info(f"Task {task_id} completed successfully. Output: {md_path}")
                
            except Exception as e:
                self.db.add_log(task_id, "ERROR", f"Processing error: {str(e)}")
                raise
                
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.
        
        Args:
            task_id: Task UUID.
            
        Returns:
            True if task was cancelled, False if not found or already done.
        """
        task = self.active_tasks.get(task_id)
        if task and not task.done():
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