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
    
    def __init__(self, db_path: str = "output/tasks.db"):
        """Initialize database.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
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
                    
                    -- Time management
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    timeout_seconds INTEGER DEFAULT 3600,
                    
                    -- Error handling
                    error TEXT,
                    retry_count INTEGER DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at);
                CREATE INDEX IF NOT EXISTS idx_started_at ON tasks(started_at);
                
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_task_logs ON task_logs(task_id);
            """)
            
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
            **kwargs: Additional parameters.
        """
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    task_id, task_dir, input_filename, backend, lang,
                    formula_enable, table_enable, image_analysis,
                    start_page_id, end_page_id, server_url, timeout_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_dir, input_filename, backend, lang,
                int(formula_enable), int(table_enable), int(image_analysis),
                start_page_id, end_page_id, server_url, timeout_seconds
            ))
            
        logger.info(f"Task created: {task_id}")
        
    def update_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """Update task status.
        
        Args:
            task_id: Task UUID.
            status: New status (pending, processing, completed, failed, cancelled).
            error: Error message (optional).
        """
        now = datetime.now().isoformat()
        
        with self._conn() as conn:
            if status == "processing":
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, started_at = ?
                    WHERE task_id = ?
                """, (status, now, task_id))
            elif status in ("completed", "failed", "cancelled"):
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?, completed_at = ?, error = ?
                    WHERE task_id = ?
                """, (status, now, error, task_id))
            else:
                conn.execute("""
                    UPDATE tasks 
                    SET status = ?
                    WHERE task_id = ?
                """, (status, task_id))
                
        logger.debug(f"Task {task_id} status updated to {status}")
        
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