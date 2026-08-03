"""Task Scheduler Module

Scheduler that polls database every second to:
1. Fetch pending tasks (when active_count < max_concurrent)
2. Check timeout tasks (started_at + timeout_seconds < NOW())
"""

import asyncio
from datetime import datetime
from pathlib import Path
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
        cleanup_days: int = 30,
        cleanup_interval_seconds: float = 3600.0,
        timeout_check_enabled: bool = True
    ):
        """Initialize task scheduler.
        
        Args:
            processor: TaskProcessor instance.
            db: TaskDatabase instance.
            max_concurrent: Maximum concurrent tasks.
            poll_interval: Polling interval in seconds (default: 1.0).
            cleanup_days: Days to keep terminal tasks.
            cleanup_interval_seconds: Cleanup polling interval.
            timeout_check_enabled: Enable timeout checking (default: True).
        """
        self.processor = processor
        self.db = db
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.cleanup_days = cleanup_days
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.timeout_check_enabled = timeout_check_enabled
        self._running = False
        self._fetch_paused = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
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
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
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

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
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

    async def _cleanup_loop(self) -> None:
        """Periodically remove old terminal tasks and output files."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                if self._running and self.cleanup_days > 0:
                    deleted = await asyncio.to_thread(self.db.cleanup_old_tasks, self.cleanup_days)
                    if deleted > 0:
                        logger.info(f"Periodic cleanup removed {deleted} old tasks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(60)
                
    async def _fetch_pending_tasks(self) -> None:
        """Fetch pending tasks from database.

        Only fetch if active_count < max_concurrent.
        Uses CAS (Compare-And-Swap) for atomic status update.

        去重：同文件同参数的重复任务不重复解析。对每个 pending 任务先做去重判断：
        - 存在同键 completed 任务且产物在盘 → 复制产物改名，标记 dedup completed，不领取。
        - 存在同键 processing 任务（非自身）→ 保持 pending 等待，不领取。
        - 否则正常领取；批内 `claimed_keys` 防止同一批内领取两个同键任务（并发防护）。
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
        
        claimed_keys: set[str] = set()
        
        for task_data in tasks:
            task_id = task_data['task_id']
            
            # 去重判断（file_hash 为 NULL 的历史任务无去重能力，直接领取）
            dedup_key = self.db.dedup_key_for_task(task_data)
            if dedup_key is not None:
                if dedup_key in claimed_keys:
                    logger.debug(f"Task {task_id} skipped: same dedup key already claimed this round")
                    continue

                # 分支 1：存在同键 completed 任务且产物可复用 → 直接完成，不解析
                source = self.db.find_dedup_source(dedup_key, exclude_task_id=task_id)
                if source is not None:
                    reused = self._complete_via_dedup(task_data, source)
                    if reused:
                        continue
                    # 复制失败（源产物缺失/被清理）→ 退化为真实解析，走下方领取

                # 分支 2：存在同键正在解析/已领取的任务 → 保持 pending 等待
                peer = self.db.find_active_dedup_peer(dedup_key, exclude_task_id=task_id)
                if peer is not None:
                    logger.debug(
                        f"Task {task_id} waits: dedup key {dedup_key[:16]}... "
                        f"already active as {peer['task_id']}"
                    )
                    continue

            now = datetime.now().isoformat()
            
            updated = self.db.execute("""
                UPDATE tasks 
                SET status = 'processing', started_at = ?, updated_at = ?, progress = 0,
                    error = NULL, message = 'Starting processing'
                WHERE status = 'pending' AND task_id = ?
            """, (now, now, task_id))
            
            if updated > 0:
                if dedup_key is not None:
                    claimed_keys.add(dedup_key)
                task_data_updated = self.db.get_task(task_id)
                asyncio.create_task(self.processor.process_task(task_id, task_data_updated))
                logger.info(f"Fetched task {task_id} for processing")
            else:
                logger.warning(f"Failed to update task {task_id} status (already taken by another scheduler)")

    def _complete_via_dedup(self, task_data: dict, source: dict) -> bool:
        """复制源任务产物到目标任务并按目标改名，标记 dedup completed。

        返回 True 表示去重完成成功；False 表示源产物不可用，需退化为真实解析。
        去重完成的任务若启用后处理，同样创建 auto run（后处理独立执行）。
        """
        task_id = task_data["task_id"]
        try:
            from .file_manager import FileManager, resolve_stored_filename

            source_dir = Path(source["task_dir"])
            target_dir = Path(task_data["task_dir"])
            source_stored = resolve_stored_filename(source["task_id"], source["input_filename"], source_dir)
            target_stored = resolve_stored_filename(task_id, task_data["input_filename"], target_dir)

            file_manager = FileManager(output_root=str(self.db.db_path.parent))
            copied = file_manager.copy_outputs_for_dedup(
                source_task_dir=source_dir,
                source_input_filename=source_stored,
                source_backend=source["backend"],
                target_task_dir=target_dir,
                target_input_filename=target_stored,
                target_backend=task_data["backend"],
            )
            if not copied:
                logger.warning(f"Task {task_id} dedup copy from {source['task_id']} failed; real parsing")
                return False

            if not self.db.mark_dedup_completed(task_id, source["task_id"]):
                logger.warning(f"Task {task_id} dedup completion race; falling back to real parsing")
                return False

            self.db.add_log(task_id, "INFO", f"Reused parsing result from task {source['task_id']}")
            if bool(task_data.get("enable_postprocess", 0)):
                self.processor.queue_auto_postprocess(task_id, task_data)
            return True
        except Exception as exc:
            logger.error(f"Task {task_id} dedup completion error: {exc}; falling back to real parsing")
            return False
            
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
