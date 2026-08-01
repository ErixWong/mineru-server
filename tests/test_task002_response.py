"""
Tests for Task-002: Response Model Standardization

Covers:
  - Pydantic response models
  - Database schema migration (_migrate)
  - Progress tracking fields
  - Error format alignment (error/message/detail)
  - Health response with scheduler/auth/queue
  - Cancel with CAS
"""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ── Models ──────────────────────────────────────────────────────────

class TestModels:
    """Pydantic model serialization tests."""

    def test_health_response_serialization(self):
        from mineru_mcp.models import HealthResponse, QueueStatsResponse

        qs = QueueStatsResponse(pending=1, processing=2, completed=3, failed=4, cancelled=5)
        resp = HealthResponse(
            status="healthy",
            version="0.2.0",
            uptime=12.5,
            scheduler_running=True,
            auth_required=False,
            queue_stats=qs,
        )
        d = resp.model_dump()
        assert d["status"] == "healthy"
        assert d["version"] == "0.2.0"
        assert d["uptime"] == 12.5
        assert d["scheduler_running"] is True
        assert d["auth_required"] is False
        assert d["queue_stats"]["pending"] == 1
        assert d["queue_stats"]["processing"] == 2

    def test_submit_task_response(self):
        from mineru_mcp.models import SubmitTaskResponse

        now = datetime.now()
        resp = SubmitTaskResponse(task_id="abc-123", message="ok", created_at=now)
        d = resp.model_dump()
        assert d["task_id"] == "abc-123"
        assert d["message"] == "ok"

    def test_task_status_response(self):
        from mineru_mcp.models import TaskStatus, TaskStatusResponse

        now = datetime.now()
        resp = TaskStatusResponse(
            task_id="x",
            status=TaskStatus.PROCESSING,
            progress=50,
            message="Working...",
            created_at=now,
            updated_at=now,
        )
        d = resp.model_dump()
        assert d["status"] == "processing"
        assert d["progress"] == 50

    def test_task_result_response(self):
        from mineru_mcp.models import TaskStatus, TaskResultResponse

        resp = TaskResultResponse(task_id="x", status=TaskStatus.COMPLETED, format="markdown", markdown="# Hello", content="# Hello", filename="input.md", error=None)
        d = resp.model_dump()
        assert d["format"] == "markdown"
        assert d["markdown"] == "# Hello"
        assert d["filename"] == "input.md"
        assert d["error"] is None

    def test_task_artifacts_response(self):
        from mineru_mcp.models import TaskStatus, TaskArtifactItem, TaskArtifactsResponse

        resp = TaskArtifactsResponse(
            task_id="x",
            status=TaskStatus.COMPLETED,
            artifacts=[
                TaskArtifactItem(
                    name="markdown",
                    kind="file",
                    filename="input.md",
                    media_type="text/markdown",
                    role="primary",
                    available=True,
                    downloadable=True,
                )
            ],
        )
        d = resp.model_dump()
        assert d["artifacts"][0]["name"] == "markdown"
        assert d["artifacts"][0]["role"] == "primary"

    def test_error_response_detail_type(self):
        from mineru_mcp.models import ErrorResponse

        resp = ErrorResponse(status="error", error="TASK_NOT_FOUND", message="gone", detail={"task_id": "abc"})
        d = resp.model_dump()
        assert d["detail"] == {"task_id": "abc"}


# ── Validation error format ─────────────────────────────────────────

class TestValidationErrorFormat:
    """ValidationError.to_dict() now outputs status/error/message/detail."""

    def test_validation_error_new_format(self):
        from mineru_mcp.validation import ValidationError

        err = ValidationError("INVALID_BACKEND", "bad backend", {"backend": "foo"})
        d = err.to_dict()

        assert d["status"] == "error"
        assert d["error"] == "INVALID_BACKEND"
        assert d["message"] == "bad backend"
        assert d["detail"] == {"backend": "foo"}
        # Old keys must NOT exist
        assert "error_code" not in d
        assert "error_message" not in d
        assert "error_details" not in d

    def test_validation_error_no_details(self):
        from mineru_mcp.validation import ValidationError

        err = ValidationError("EMPTY_FILE", "no content")
        d = err.to_dict()
        assert d["detail"] is None


# ── MCPError format ─────────────────────────────────────────────────

class TestMCPErrorFormat:
    """MCPError.to_dict() now outputs error/message/detail."""

    def test_mcp_error_new_format(self):
        from mineru_mcp.errors import MCPError, ErrorCode

        err = MCPError(code=ErrorCode.TASK_NOT_FOUND, message="not found", details={"task_id": "x"}, http_status=404)
        d = err.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "TASK_NOT_FOUND"
        assert d["message"] == "not found"
        assert d["detail"] == {"task_id": "x"}
        assert "error_code" not in d
        assert "error_message" not in d
        assert "error_details" not in d


# ── Database migration ──────────────────────────────────────────────

class TestDatabaseMigration:
    """_migrate() adds missing columns to existing tasks table."""

    def test_migration_on_fresh_db(self):
        """New DB already has all columns — migration is idempotent."""
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))

            with db._conn() as conn:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            assert "progress" in cols
            assert "message" in cols
            assert "updated_at" in cols

    def test_migration_on_old_db(self):
        """Simulate old DB that lacks progress/message/updated_at columns."""
        import sqlite3
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"

            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    task_dir TEXT NOT NULL,
                    input_filename TEXT NOT NULL,
                    backend TEXT DEFAULT 'vlm-auto-engine',
                    lang TEXT DEFAULT 'ch',
                    formula_enable INTEGER DEFAULT 1,
                    table_enable INTEGER DEFAULT 1,
                    image_analysis INTEGER DEFAULT 1,
                    server_url TEXT,
                    return_md INTEGER DEFAULT 1,
                    start_page_id INTEGER DEFAULT 0,
                    end_page_id INTEGER DEFAULT 99999,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    timeout_seconds INTEGER DEFAULT 3600,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0
                );
            """)
            conn.commit()
            conn.close()

            # Now open with TaskDatabase — it must migrate
            db = TaskDatabase(db_path=str(db_path))

            with db._conn() as conn:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            assert "progress" in cols
            assert "message" in cols
            assert "updated_at" in cols


# ── Progress tracking ───────────────────────────────────────────────

class TestProgressTracking:
    """update_status and update_progress correctly write progress/message."""

    def test_status_updates_progress(self):
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))

            db.create_task(task_id="t1", task_dir=str(tmp), input_filename="a.pdf")
            db.update_status("t1", "processing", progress=0, message="Starting")
            task = db.get_task("t1")
            assert task["status"] == "processing"
            assert task["progress"] == 0
            assert task["message"] == "Starting"

            db.update_status("t1", "completed", progress=100, message="Done")
            task = db.get_task("t1")
            assert task["status"] == "completed"
            assert task["progress"] == 100
            assert task["message"] == "Done"

    def test_update_progress_mid_flow(self):
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))

            db.create_task(task_id="t2", task_dir=str(tmp), input_filename="b.pdf")
            db.update_progress("t2", 50, "Halfway")
            task = db.get_task("t2")
            assert task["status"] == "processing"
            assert task["progress"] == 50
            assert task["message"] == "Halfway"

    def test_failed_cancelled_progress_minus_one(self):
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))

            db.create_task(task_id="t3", task_dir=str(tmp), input_filename="c.pdf")
            db.update_status("t3", "failed", error="boom", progress=-1, message="Failed")
            task = db.get_task("t3")
            assert task["status"] == "failed"
            assert task["progress"] == -1

            db.create_task(task_id="t4", task_dir=str(tmp), input_filename="d.pdf")
            db.update_status("t4", "cancelled", message="Cancelled")
            task = db.get_task("t4")
            assert task["status"] == "cancelled"
            assert task["progress"] == -1


# ── Cancel with CAS ─────────────────────────────────────────────────

class TestCancelCAS:
    """Cancel via DB uses CAS WHERE to prevent double-writes."""

    def test_cancel_cas_only_updates_non_terminal(self):
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))

            db.create_task(task_id="c1", task_dir=str(tmp), input_filename="x.pdf")
            db.update_status("c1", "pending")

            now = datetime.now().isoformat()
            updated = db.execute(
                "UPDATE tasks SET status = 'cancelled', message = 'x', completed_at = ?, updated_at = ? WHERE task_id = ? AND status != 'cancelled'",
                (now, now, "c1")
            )
            assert updated > 0
            task = db.get_task("c1")
            assert task["status"] == "cancelled"

            # Second attempt on already cancelled — must return 0
            updated2 = db.execute(
                "UPDATE tasks SET status = 'cancelled', message = 'y', completed_at = ?, updated_at = ? WHERE task_id = ? AND status != 'cancelled'",
                (now, now, "c1")
            )
            assert updated2 == 0


# ── Retry and cleanup ────────────────────────────────────────────────

class TestRetryAndCleanup:
    """Retry and cleanup config should have concrete behavior."""

    def test_fail_requeues_until_retry_limit(self):
        from mineru_mcp.task_queue.database import TaskDatabase
        from mineru_mcp.task_queue.state_service import TaskStateService

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            db = TaskDatabase(db_path=str(db_path))
            db.create_task(
                task_id="retry-task",
                task_dir=str(Path(tmp) / "retry-task"),
                input_filename="x.pdf",
                timeout_seconds=3600,
            )
            db.execute("UPDATE tasks SET status = 'processing' WHERE task_id = ?", ("retry-task",))

            state = TaskStateService(db, retry_limit=1)
            assert state.fail("retry-task", "first failure") is True
            task = db.get_task("retry-task")
            assert task["status"] == "pending"
            assert task["retry_count"] == 1

            db.execute("UPDATE tasks SET status = 'processing' WHERE task_id = ?", ("retry-task",))
            assert state.fail("retry-task", "second failure") is True
            task = db.get_task("retry-task")
            assert task["status"] == "failed"
            assert task["retry_count"] == 1

    def test_cleanup_old_tasks_removes_output_directory(self):
        from mineru_mcp.task_queue.database import TaskDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            task_dir = Path(tmp) / "old-task"
            task_dir.mkdir()
            (task_dir / "artifact.md").write_text("done", encoding="utf-8")

            db = TaskDatabase(db_path=str(db_path))
            db.create_task(task_id="old-task", task_dir=str(task_dir), input_filename="x.pdf")
            completed_at = (datetime.now() - timedelta(days=10)).isoformat()
            db.execute(
                "UPDATE tasks SET status = 'completed', completed_at = ?, updated_at = ? WHERE task_id = ?",
                (completed_at, completed_at, "old-task"),
            )

            assert db.cleanup_old_tasks(days=1) == 1
            assert db.get_task("old-task") is None
            assert not task_dir.exists()


# ── Health visibility ────────────────────────────────────────────────

class TestHealthVisibility:
    """HealthResponse carries scheduler/auth/queue fields."""

    def test_health_degraded_when_scheduler_down(self):
        from mineru_mcp.models import HealthResponse

        resp = HealthResponse(
            status="degraded",
            version="0.2.0",
            uptime=1.0,
            scheduler_running=False,
            auth_required=True,
            queue_stats=None,
        )
        d = resp.model_dump()
        assert d["status"] == "degraded"
        assert d["scheduler_running"] is False
        assert d["auth_required"] is True
        assert d["queue_stats"] is None

    def test_health_with_stats(self):
        from mineru_mcp.models import HealthResponse, QueueStatsResponse

        qs = QueueStatsResponse(pending=0, processing=1, completed=5, failed=2, cancelled=1)
        resp = HealthResponse(
            status="healthy",
            version="0.2.0",
            uptime=60.0,
            scheduler_running=True,
            auth_required=False,
            queue_stats=qs,
        )
        d = resp.model_dump()
        assert d["queue_stats"]["processing"] == 1
        assert d["queue_stats"]["completed"] == 5

    def test_queue_stats_wrapper_has_total(self):
        from mineru_mcp.models import QueueStatsResponse, QueueStatsWrapper

        qs = QueueStatsResponse(pending=1, processing=2, completed=3, failed=4, cancelled=5)
        wrapper = QueueStatsWrapper(queue_stats=qs, total=15)
        d = wrapper.model_dump()
        assert d["queue_stats"]["pending"] == 1
        assert d["total"] == 15
