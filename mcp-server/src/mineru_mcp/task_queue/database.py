"""Task Database Module

SQLite-based task storage with WAL mode for better concurrency.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from loguru import logger


class TaskDatabase:
    """SQLite database for task queue management."""
    
    SCHEMA_VERSION = 4

    def __init__(self, db_path: str = "output/tasks.db"):
        """Initialize database.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        self._migrate()
        logger.info(f"TaskDatabase initialized at {self.db_path}")
        
    def _init_tables(self):
        """Initialize database tables."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    task_dir TEXT NOT NULL,
                    input_filename TEXT NOT NULL,
                    
                    -- Owner (for task isolation)
                    owner_id TEXT NOT NULL,
                    owner_type TEXT NOT NULL DEFAULT 'single_user',
                    
                    -- MinerU parameters
                    backend TEXT DEFAULT 'vlm-auto-engine',
                    parse_method TEXT DEFAULT 'auto',
                    lang TEXT DEFAULT 'ch',
                    formula_enable INTEGER DEFAULT 1,
                    table_enable INTEGER DEFAULT 1,
                    image_analysis INTEGER DEFAULT 1,
                    server_url TEXT,
                    
                    -- Output options
                    return_md INTEGER DEFAULT 1,
                    return_middle_json INTEGER DEFAULT 0,
                    return_model_output INTEGER DEFAULT 0,
                    return_content_list INTEGER DEFAULT 0,
                    return_images INTEGER DEFAULT 0,
                    
                    -- Page range
                    start_page_id INTEGER DEFAULT 0,
                    end_page_id INTEGER DEFAULT 99999,
                    
                    -- Progress tracking
                    progress INTEGER DEFAULT 0,
                    message TEXT DEFAULT 'Task created',
                    
                    -- Time management
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    timeout_seconds INTEGER DEFAULT 3600,
                    
                    -- Error handling
                    error TEXT,
                    retry_count INTEGER DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at);
                CREATE INDEX IF NOT EXISTS idx_started_at ON tasks(started_at);
                CREATE INDEX IF NOT EXISTS idx_owner_id ON tasks(owner_id);
                
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_task_logs ON task_logs(task_id);

                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'uploaded',
                    file_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    -- Owner (for upload isolation)
                    owner_id TEXT NOT NULL,
                    owner_type TEXT NOT NULL DEFAULT 'single_user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    consumed_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_upload_status ON uploads(status);
                CREATE INDEX IF NOT EXISTS idx_upload_owner_id ON uploads(owner_id);
            """)

    def _migrate(self):
        """Apply schema migrations for backward compatibility.
        
        Uses PRAGMA user_version for version tracking.
        Each version step is atomic and idempotent.
        """
        with self._conn() as conn:
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]

            if current_version < 1:
                logger.info(f"Running schema migration v0 -> v1")
                self._migrate_v1(conn)
                conn.execute(f"PRAGMA user_version = 1")
                current_version = 1

            if current_version < 2:
                logger.info(f"Running schema migration v1 -> v2")
                self._migrate_v2(conn)
                conn.execute(f"PRAGMA user_version = 2")
                current_version = 2

            if current_version < 3:
                logger.info(f"Running schema migration v2 -> v3")
                self._migrate_v3(conn)
                conn.execute(f"PRAGMA user_version = 3")
                current_version = 3
            
            if current_version < 4:
                logger.info(f"Running schema migration v3 -> v4")
                self._migrate_v4(conn)
                conn.execute(f"PRAGMA user_version = 4")
                current_version = 4

    def _migrate_v1(self, conn):
        """V1: original table creation (handled by CREATE TABLE IF NOT EXISTS)."""

    def _migrate_v2(self, conn):
        """V2: add progress/message/updated_at columns (no non-constant defaults)."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

        v2_columns = [
            ("progress", "ALTER TABLE tasks ADD COLUMN progress INTEGER DEFAULT 0"),
            ("message", "ALTER TABLE tasks ADD COLUMN message TEXT"),
            ("updated_at", "ALTER TABLE tasks ADD COLUMN updated_at TIMESTAMP"),
        ]

        for col, sql in v2_columns:
            if col not in existing:
                conn.execute(sql)
                logger.info(f"Migration v2: added column '{col}' to tasks table")

    def _migrate_v3(self, conn):
        """V3: create uploads table for staged file submission."""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS uploads (
                upload_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'uploaded',
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                consumed_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_upload_status ON uploads(status);
        """)
    
    def _migrate_v4(self, conn):
        """V4: add owner_id and owner_type to tasks and uploads tables."""
        # Add columns to tasks table
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        
        if "owner_id" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local-default'")
            logger.info("Migration v4: added column 'owner_id' to tasks table")
        
        if "owner_type" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'single_user'")
            logger.info("Migration v4: added column 'owner_type' to tasks table")
        
        # Add index on owner_id if not exists
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_owner_id ON tasks(owner_id)")
        except sqlite3.OperationalError:
            pass  # Index may already exist
        
        # Add columns to uploads table
        existing_uploads_cols = {row[1] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()}
        
        if "owner_id" not in existing_uploads_cols:
            conn.execute("ALTER TABLE uploads ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local-default'")
            logger.info("Migration v4: added column 'owner_id' to uploads table")
        
        if "owner_type" not in existing_uploads_cols:
            conn.execute("ALTER TABLE uploads ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'single_user'")
            logger.info("Migration v4: added column 'owner_type' to uploads table")
        
        # Add index on owner_id if not exists
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_owner_id ON uploads(owner_id)")
        except sqlite3.OperationalError:
            pass  # Index may already exist
        
        logger.info("Migration v4: completed owner columns migration")
            
    @contextmanager
    def _conn(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
            
    def create_task(
        self,
        task_id: str,
        task_dir: str,
        input_filename: str,
        backend: str = "vlm-auto-engine",
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        image_analysis: bool = True,
        start_page_id: int = 0,
        end_page_id: int = 99999,
        server_url: Optional[str] = None,
        timeout_seconds: int = 3600,
        owner_id: str = "local-default",
        owner_type: str = "single_user",
        **kwargs
    ) -> None:
        """Create a new task.
        
        Args:
            task_id: UUID for the task.
            task_dir: Task directory path (output/2026/05/10/{uuid}/).
            input_filename: Input file name (input.pdf).
            backend: MinerU backend type.
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            image_analysis: Enable image analysis.
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            server_url: VLM server URL (for http-client backend).
            timeout_seconds: Task timeout in seconds.
            owner_id: Owner identifier for task isolation.
            owner_type: Owner type (api_key, proxy_header, single_user).
            **kwargs: Additional parameters.
        """
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    task_id, task_dir, input_filename, backend, lang,
                    formula_enable, table_enable, image_analysis,
                    start_page_id, end_page_id, server_url, timeout_seconds,
                    owner_id, owner_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_dir, input_filename, backend, lang,
                int(formula_enable), int(table_enable), int(image_analysis),
                start_page_id, end_page_id, server_url, timeout_seconds,
                owner_id, owner_type
            ))
            
        logger.info(f"Task created: {task_id} (owner={owner_id})")
        
    def update_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None
    ) -> None:
        """Update task status.
        
        Args:
            task_id: Task UUID.
            status: New status (pending, processing, completed, failed, cancelled).
            error: Error message (optional).
            progress: Progress percentage (optional, 0-100, -1 for failed/cancelled).
            message: Status message (optional).
        """
        now = datetime.now().isoformat()
        
        with self._conn() as conn:
            if status == "processing":
                prog = progress if progress is not None else 0
                msg = message if message is not None else "Processing started"
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, started_at = ?, updated_at = ?, progress = ?, message = ?
                    WHERE task_id = ?
                """, (status, now, now, prog, msg, task_id))
            elif status == "completed":
                prog = progress if progress is not None else 100
                msg = message if message is not None else "Conversion completed"
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, completed_at = ?, updated_at = ?, progress = ?, message = ?
                    WHERE task_id = ?
                """, (status, now, now, prog, msg, task_id))
            elif status in ("failed", "cancelled"):
                prog = progress if progress is not None else -1
                msg = message if message is not None else (error or f"Task {status}")
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, completed_at = ?, updated_at = ?, error = ?, progress = ?, message = ?
                    WHERE task_id = ?
                """, (status, now, now, error, prog, msg, task_id))
            else:
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, updated_at = ?
                    WHERE task_id = ?
                """, (status, now, task_id))
                
        logger.debug(f"Task {task_id} status updated to {status}")
        
    def update_progress(
        self,
        task_id: str,
        progress: int,
        message: str
    ) -> None:
        """Update task progress.
        
        Args:
            task_id: Task UUID.
            progress: Progress percentage (0-100).
            message: Status message.
        """
        now = datetime.now().isoformat()
        
        with self._conn() as conn:
            conn.execute("""
                UPDATE tasks 
                SET status = ?, progress = ?, message = ?, updated_at = ?
                WHERE task_id = ?
            """, ("processing", progress, message, now, task_id))
                
        logger.debug(f"Task {task_id} progress updated to {progress}%")
        
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID.
        
        Args:
            task_id: Task UUID.
            
        Returns:
            Task data dict or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", 
                (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_upload(
        self,
        upload_id: str,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        file_path: str,
        owner_id: str = "local-default",
        owner_type: str = "single_user",
    ) -> None:
        """Create an uploaded file record.
        
        Args:
            upload_id: Unique upload identifier.
            file_name: Name of the uploaded file.
            mime_type: MIME type of the file.
            size_bytes: Size of the file in bytes.
            sha256: SHA256 hash of the file.
            file_path: Path to the stored file.
            owner_id: Owner identifier for upload isolation.
            owner_type: Owner type (api_key, proxy_header, single_user).
        """
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO uploads (
                    upload_id, file_name, mime_type, size_bytes, sha256, file_path,
                    owner_id, owner_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (upload_id, file_name, mime_type, size_bytes, sha256, file_path, owner_id, owner_type))
        
        logger.info(f"Upload created: {upload_id} (owner={owner_id})")

    def get_upload(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """Get uploaded file record by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM uploads WHERE upload_id = ?",
                (upload_id,)
            ).fetchone()
            return dict(row) if row else None

    def consume_upload(self, upload_id: str) -> bool:
        """Mark an upload as consumed exactly once."""
        now = datetime.now().isoformat()
        updated = self.execute(
            "UPDATE uploads SET status = 'consumed', consumed_at = ? WHERE upload_id = ? AND status = 'uploaded'",
            (now, upload_id),
        )
        return updated > 0

    def release_upload(self, upload_id: str) -> bool:
        """Release a previously consumed upload back to uploaded state."""
        updated = self.execute(
            "UPDATE uploads SET status = 'uploaded', consumed_at = NULL WHERE upload_id = ? AND status = 'consumed'",
            (upload_id,),
        )
        return updated > 0
            
    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch one record.
        
        Args:
            sql: SQL query.
            params: Query parameters.
            
        Returns:
            Record dict or None.
        """
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
            
    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all records.
        
        Args:
            sql: SQL query.
            params: Query parameters.
            
        Returns:
            List of record dicts.
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
            
    def count(self, sql: str, params: tuple = ()) -> int:
        """Count records.
        
        Args:
            sql: SQL query (should return COUNT(*)).
            params: Query parameters.
            
        Returns:
            Count value.
        """
        with self._conn() as conn:
            result = conn.execute(sql, params).fetchone()
            return result[0] if result else 0
            
    def add_log(self, task_id: str, level: str, message: str) -> None:
        """Add task log.
        
        Args:
            task_id: Task UUID.
            level: Log level (INFO, WARNING, ERROR).
            message: Log message.
        """
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO task_logs (task_id, level, message)
                VALUES (?, ?, ?)
            """, (task_id, level, message))
            
    def get_logs(self, task_id: str) -> List[Dict[str, Any]]:
        """Get task logs.
        
        Args:
            task_id: Task UUID.
            
        Returns:
            List of log dicts.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM task_logs WHERE task_id = ? ORDER BY created_at",
                (task_id,)
            ).fetchall()
            return [dict(row) for row in rows]
            
    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute SQL and return affected row count.
        
        Args:
            sql: SQL query.
            params: Query parameters.
            
        Returns:
            Number of affected rows.
        """
        with self._conn() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount
            
    def cleanup_old_tasks(self, days: int = 30) -> int:
        """Clean up old completed/failed tasks.
        
        Args:
            days: Days to keep (delete older than this).
            
        Returns:
            Number of tasks deleted.
        """
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        with self._conn() as conn:
            # Get old tasks
            old_tasks = conn.execute("""
                SELECT task_id, task_dir FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            """, (cutoff_str,)).fetchall()
            
            # Delete from database
            conn.execute("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            """, (cutoff_str,))
            
            # Delete logs
            for task in old_tasks:
                conn.execute("DELETE FROM task_logs WHERE task_id = ?", (task['task_id'],))
                
        deleted_count = len(old_tasks)
        logger.info(f"Cleaned up {deleted_count} old tasks")
        return deleted_count
