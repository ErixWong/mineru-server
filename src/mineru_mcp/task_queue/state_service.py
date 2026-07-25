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

    def __init__(self, db):
        self.db = db

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
        """Mark a task as failed (CAS: only processing tasks).

        Returns True if the transition succeeded.
        """
        now = datetime.now().isoformat()
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
