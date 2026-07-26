"""Task Scheduler Module

Scheduler that polls database every second to:
1. Fetch pending tasks (when active_count < max_concurrent)
2. Check timeout tasks (started_at + timeout_seconds < NOW())
"""

import asyncio
from datetime import datetime
from typing import Optional

from loguru import logger

from .database import TaskDatabase
from .processor import TaskProcessor
from .state_service import TaskStateService


class TaskScheduler:
    """Task scheduler with clock-based polling.
    
    Runs in the same process as MCP Server (not a separate process).
    
    IMPORTANT: Single-instance design
        - Current architecture assumes ONE scheduler instance per deployment
        - CAS (Compare-And-Swap) update prevents duplicate task pickup within same instance
        - Multi-instance deployment would require distributed locking (Redis/etcd)
        - Current Dockerfile is designed for single-container deployment
    """
    
    def __init__(
        self,
        processor: TaskProcessor,
        db: TaskDatabase,
        max_concurrent: int = 3,
        poll_interval: float = 1.0,
        timeout_check_enabled: bool = True
    ):
        """Initialize task scheduler.
        
        Args:
            processor: TaskProcessor instance.
            db: TaskDatabase instance.
            max_concurrent: Maximum concurrent tasks.
            poll_interval: Polling interval in seconds (default: 1.0).
            timeout_check_enabled: Enable timeout checking (default: True).
        """
        self.processor = processor
        self.db = db
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.timeout_check_enabled = timeout_check_enabled
        self._running = False
        self._fetch_paused = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        logger.info(f"TaskScheduler initialized: max_concurrent={max_concurrent}, poll_interval={poll_interval}s")

    def pause_fetching(self) -> None:
        """Pause claiming new pending tasks while keeping timeout checks alive."""
        self._fetch_paused = True
        logger.info("TaskScheduler pending-task fetching paused")

    def resume_fetching(self) -> None:
        """Resume claiming new pending tasks."""
        self._fetch_paused = False
        logger.info("TaskScheduler pending-task fetching resumed")
        
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return
            
        self._running = True
        self._scheduler_task = asyncio.create_task(self._poll_loop())
        logger.info("TaskScheduler started")
        
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return
            
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
                
        logger.info("TaskScheduler stopped")
        
    async def _poll_loop(self) -> None:
        """Main polling loop (clock).
        
        Every poll_interval seconds:
        1. Fetch pending tasks (if active_count < max_concurrent)
        2. Check timeout tasks (if enabled)
        """
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                
                await self._fetch_pending_tasks()
                
                if self._running and self.timeout_check_enabled:
                    await self._check_timeout_tasks()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(5)
                
    async def _fetch_pending_tasks(self) -> None:
        """Fetch pending tasks from database.
        
        Only fetch if active_count < max_concurrent.
        Uses CAS (Compare-And-Swap) for atomic status update.
        """
        active_count = self.processor.get_active_count()

        if self._fetch_paused:
            logger.debug("Pending-task fetching is paused, skipping fetch")
            return
        
        if active_count >= self.max_concurrent:
            logger.debug(f"Max concurrent reached ({active_count}/{self.max_concurrent}), skipping fetch")
            return
            
        available_slots = self.max_concurrent - active_count
        
        tasks = self.db.fetch_all(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (available_slots,)
        )
        
        for task_data in tasks:
            task_id = task_data['task_id']
            
            now = datetime.now().isoformat()
            
            updated = self.db.execute("""
                UPDATE tasks 
                SET status = 'processing', started_at = ?, updated_at = ?, progress = 0, message = 'Starting processing'
                WHERE status = 'pending' AND task_id = ?
            """, (now, now, task_id))
            
            if updated > 0:
                task_data_updated = self.db.get_task(task_id)
                asyncio.create_task(self.processor.process_task(task_id, task_data_updated))
                logger.info(f"Fetched task {task_id} for processing")
            else:
                logger.warning(f"Failed to update task {task_id} status (already taken by another scheduler)")
            
    async def _check_timeout_tasks(self) -> None:
        """Check timeout tasks.
        
        Find tasks where started_at + timeout_seconds < NOW().
        """
        now = datetime.now()
        
        processing_tasks = self.db.fetch_all(
            "SELECT task_id, started_at, timeout_seconds FROM tasks WHERE status = 'processing' AND started_at IS NOT NULL"
        )
        
        for task_data in processing_tasks:
            task_id = task_data['task_id']
            started_at_str = task_data['started_at']
            timeout_seconds = task_data['timeout_seconds']
            
            try:
                started_at = datetime.fromisoformat(started_at_str)
                elapsed = (now - started_at).total_seconds()
                
                if elapsed >= timeout_seconds:
                    logger.warning(f"Task {task_id} timeout: elapsed={elapsed}s, limit={timeout_seconds}s")
                    
                    self.processor.cancel_task(task_id)
                    
                    state = TaskStateService(self.db)
                    state.timeout(task_id, elapsed)
                    
            except Exception as e:
                logger.error(f"Error checking timeout for task {task_id}: {e}")
                
    def recover_processing_tasks(self) -> int:
        """Recover processing tasks on startup.
        
        Called when MCP Server restarts to recover tasks that were
        marked as 'processing' before the restart.
        
        Returns:
            Number of tasks recovered.
        """
        processing_tasks = self.db.fetch_all(
            "SELECT task_id FROM tasks WHERE status = 'processing'"
        )
        
        recovered_count = 0
        for task_data in processing_tasks:
            task_id = task_data['task_id']
            
            self.db.update_status(task_id, "pending")
            self.db.add_log(task_id, "INFO", "Task recovered after server restart")
            recovered_count += 1
            
        if recovered_count > 0:
            logger.info(f"Recovered {recovered_count} processing tasks on startup")
            
        return recovered_count
        
    def get_stats(self) -> dict:
        """Get scheduler statistics.
        
        Returns:
            Dict with scheduler stats.
        """
        pending_count = self.db.count("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
        processing_count = self.db.count("SELECT COUNT(*) FROM tasks WHERE status = 'processing'")
        completed_count = self.db.count("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
        failed_count = self.db.count("SELECT COUNT(*) FROM tasks WHERE status = 'failed'")
        cancelled_count = self.db.count("SELECT COUNT(*) FROM tasks WHERE status = 'cancelled'")
        
        return {
            "pending": pending_count,
            "processing": processing_count,
            "completed": completed_count,
            "failed": failed_count,
            "cancelled": cancelled_count,
            "active": self.processor.get_active_count(),
            "max_concurrent": self.max_concurrent,
            "running": self._running,
        }
