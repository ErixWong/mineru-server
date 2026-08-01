"""Task State Service

Centralized state machine for task transitions.
All cancel/timeout/complete/fail operations go through this single entry point
to ensure CAS-protected atomicity and consistent progress tracking.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from loguru import logger


class TaskStateService:
    """Centralized task state machine with CAS-protected transitions."""

    def __init__(self, db, retry_limit: int = 0):
        self.db = db
        self.retry_limit = max(0, int(retry_limit or 0))

    def cancel(self, task_id: str, reason: str = "Task cancelled by user") -> bool:
        """Cancel a task (CAS: only pending/processing tasks).

        Returns True if the transition succeeded, False if already terminal.
        """
        now = datetime.now().isoformat()
        updated = self.db.execute(
            "UPDATE tasks SET status = 'cancelled', progress = -1, error = ?,"
            " message = ?, completed_at = ?, updated_at = ?"
            " WHERE task_id = ? AND status IN ('pending','processing')",
            (reason, reason, now, now, task_id),
        )
        if updated > 0:
            logger.info(f"TaskStateService: cancelled {task_id}")
            return True
        logger.debug(f"TaskStateService: cancel skipped for {task_id} (already terminal)")
        return False

    def timeout(self, task_id: str, elapsed: float) -> bool:
        """Mark a task as timed out (CAS: only processing tasks → cancelled).

        Returns True if the transition succeeded.
        """
        now = datetime.now().isoformat()
        reason = f"Timeout after {elapsed:.0f}s"
        updated = self.db.execute(
            "UPDATE tasks SET status = 'cancelled', progress = -1, error = ?,"
            " message = ?, completed_at = ?, updated_at = ?"
            " WHERE task_id = ? AND status = 'processing'",
            (reason, reason, now, now, task_id),
        )
        if updated > 0:
            logger.info(f"TaskStateService: timeout {task_id}")
            self.db.add_log(task_id, "ERROR", f"Task timeout: {elapsed:.0f}s")
            return True
        return False

    def complete(self, task_id: str) -> bool:
        """Mark a task as completed (CAS: only processing tasks).

        Returns True if the transition succeeded.
        """
        now = datetime.now().isoformat()
        updated = self.db.execute(
            "UPDATE tasks SET status = 'completed', progress = 100,"
            " message = 'Conversion completed', completed_at = ?, updated_at = ?"
            " WHERE task_id = ? AND status = 'processing'",
            (now, now, task_id),
        )
        if updated > 0:
            logger.info(f"TaskStateService: completed {task_id}")
            return True
        return False

    def fail(self, task_id: str, error: str) -> bool:
        """Mark a task as failed or requeue it when retry budget remains.

        Returns True if the transition succeeded.
        """
        now = datetime.now().isoformat()
        task = self.db.get_task(task_id)
        if task:
            retry_count = int(task.get("retry_count") or 0)
            retry_limit = self.retry_limit
            if retry_count < retry_limit:
                next_retry = retry_count + 1
                updated = self.db.execute(
                    "UPDATE tasks SET status = 'pending', progress = 0, error = ?,"
                    " message = ?, retry_count = ?, started_at = NULL, updated_at = ?"
                    " WHERE task_id = ? AND status = 'processing' AND retry_count = ?",
                    (
                        error,
                        f"Retry {next_retry}/{retry_limit} queued after failure",
                        next_retry,
                        now,
                        task_id,
                        retry_count,
                    ),
                )
                if updated > 0:
                    logger.warning(
                        f"TaskStateService: requeued {task_id} after failure "
                        f"(retry {next_retry}/{retry_limit})"
                    )
                    self.db.add_log(task_id, "WARNING", f"Retry {next_retry}/{retry_limit}: {error[:300]}")
                    return True

        updated = self.db.execute(
            "UPDATE tasks SET status = 'failed', progress = -1, error = ?,"
            " message = ?, completed_at = ?, updated_at = ?"
            " WHERE task_id = ? AND status = 'processing'",
            (error, error, now, now, task_id),
        )
        if updated > 0:
            logger.warning(f"TaskStateService: failed {task_id}: {error[:100]}")
            return True
        return False
