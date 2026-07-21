"""Task Database Module

SQLite-based task storage with WAL mode for better concurrency.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from loguru import logger


UNSET = object()


class TaskDatabase:
    """SQLite database for task queue management."""
    
    SCHEMA_VERSION = 11

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
                    retry_count INTEGER DEFAULT 0,

                    -- Postprocess options
                    enable_postprocess INTEGER DEFAULT 0,
                    postprocess_rule_id TEXT,
                    postprocess_context_size INTEGER,
                    postprocess_status TEXT DEFAULT 'not_enabled',
                    postprocess_output_filename TEXT,
                    postprocess_rule_title_snapshot TEXT,
                    postprocess_prompt_snapshot TEXT
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

                CREATE TABLE IF NOT EXISTS postprocess_rules (
                    rule_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    output_filename TEXT NOT NULL DEFAULT 'postprocessed.md',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_postprocess_rules_enabled ON postprocess_rules(enabled);

                -- 后处理三层模型：原子动作 / 流水线方案 / 执行实例
                CREATE TABLE IF NOT EXISTS postprocess_actions (
                    action_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'llm_transform',
                    config TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_postprocess_actions_enabled ON postprocess_actions(enabled);

                CREATE TABLE IF NOT EXISTS postprocess_plans (
                    plan_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    steps TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_postprocess_plans_enabled ON postprocess_plans(enabled);

                CREATE TABLE IF NOT EXISTS postprocess_runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    plan_id TEXT,
                    plan_title_snapshot TEXT NOT NULL,
                    steps_snapshot TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    current_step INTEGER NOT NULL DEFAULT 0,
                    step_results TEXT,
                    trigger_source TEXT NOT NULL DEFAULT 'manual',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_pp_runs_task ON postprocess_runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_pp_runs_status ON postprocess_runs(status);

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

            if current_version < 5:
                logger.info(f"Running schema migration v4 -> v5")
                self._migrate_v5(conn)
                conn.execute(f"PRAGMA user_version = 5")
                current_version = 5

            if current_version < 6:
                logger.info(f"Running schema migration v5 -> v6")
                self._migrate_v6(conn)
                conn.execute(f"PRAGMA user_version = 6")
                current_version = 6

            if current_version < 7:
                logger.info(f"Running schema migration v6 -> v7")
                self._migrate_v7(conn)
                conn.execute(f"PRAGMA user_version = 7")
                current_version = 7

            if current_version < 8:
                logger.info(f"Running schema migration v7 -> v8")
                self._migrate_v8(conn)
                conn.execute(f"PRAGMA user_version = 8")
                current_version = 8

            if current_version < 9:
                logger.info(f"Running schema migration v8 -> v9")
                self._migrate_v9(conn)
                conn.execute(f"PRAGMA user_version = 9")
                current_version = 9

            if current_version < 10:
                logger.info(f"Running schema migration v9 -> v10")
                self._migrate_v10(conn)
                conn.execute(f"PRAGMA user_version = 10")
                current_version = 10

            if current_version < 11:
                logger.info(f"Running schema migration v10 -> v11")
                self._migrate_v11(conn)
                conn.execute(f"PRAGMA user_version = 11")
                current_version = 11

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
        """V3: no-op retained for historical compatibility."""
    
    def _migrate_v4(self, conn):
        """V4: add owner_id and owner_type to tasks table."""
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
        
        logger.info("Migration v4: completed owner columns migration")
            
    def _migrate_v5(self, conn):
        """V5: add callers table, admin_credentials table, and caller_id fields to tasks."""
        # Create callers table for API key management
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS callers (
                caller_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key_hash TEXT NOT NULL,
                api_key_prefix TEXT NOT NULL,
                api_key_suffix TEXT NOT NULL,
                expires_at TIMESTAMP,
                disabled INTEGER NOT NULL DEFAULT 0,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_callers_name ON callers(name);
            CREATE INDEX IF NOT EXISTS idx_callers_disabled ON callers(disabled);
            CREATE INDEX IF NOT EXISTS idx_callers_api_key_hash ON callers(api_key_hash);
            
            CREATE TABLE IF NOT EXISTS admin_credentials (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                must_change_password INTEGER DEFAULT 0,
                password_changed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Add caller_id and summary fields to tasks table
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        
        if "caller_id" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN caller_id TEXT")
            logger.info("Migration v5: added column 'caller_id' to tasks table")
        
        if "request_summary" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN request_summary TEXT")
            logger.info("Migration v5: added column 'request_summary' to tasks table")
        
        if "result_summary" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN result_summary TEXT")
            logger.info("Migration v5: added column 'result_summary' to tasks table")
        
        # Add index on caller_id if not exists
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_caller_id ON tasks(caller_id)")
        except sqlite3.OperationalError:
            pass  # Index may already exist
        
        logger.info("Migration v5: completed callers, admin_credentials, and caller_id fields migration")
    
    def _migrate_v6(self, conn):
        """V6: rename api_key_hash to api_key for plaintext storage."""
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(callers)").fetchall()}
        
        if "api_key_hash" in existing_cols and "api_key" not in existing_cols:
            conn.execute("ALTER TABLE callers RENAME COLUMN api_key_hash TO api_key")
            conn.execute("DROP INDEX IF EXISTS idx_callers_api_key_hash")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_callers_api_key ON callers(api_key)")
            logger.info("Migration v6: renamed api_key_hash to api_key (plaintext)")

    def _migrate_v7(self, conn):
        """V7: remove staged uploads tables and indexes."""
        conn.executescript("""
            DROP INDEX IF EXISTS idx_upload_status;
            DROP INDEX IF EXISTS idx_upload_owner_id;
            DROP TABLE IF EXISTS uploads;
        """)
        logger.info("Migration v7: dropped uploads table and related indexes")

    def _migrate_v8(self, conn):
        """V8: add postprocess task fields and rule table."""
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

        if "enable_postprocess" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN enable_postprocess INTEGER DEFAULT 0")
            logger.info("Migration v8: added column 'enable_postprocess' to tasks table")

        if "postprocess_rule_id" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_rule_id TEXT")
            logger.info("Migration v8: added column 'postprocess_rule_id' to tasks table")

        if "postprocess_context_size" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_context_size INTEGER")
            logger.info("Migration v8: added column 'postprocess_context_size' to tasks table")

        if "postprocess_status" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_status TEXT DEFAULT 'not_enabled'")
            logger.info("Migration v8: added column 'postprocess_status' to tasks table")

        if "postprocess_output_filename" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_output_filename TEXT")
            logger.info("Migration v8: added column 'postprocess_output_filename' to tasks table")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS postprocess_rules (
                rule_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                output_filename TEXT NOT NULL DEFAULT 'postprocessed.md',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_postprocess_rules_enabled ON postprocess_rules(enabled);
        """)

        existing_rule_cols = {row[1] for row in conn.execute("PRAGMA table_info(postprocess_rules)").fetchall()}
        if "output_filename" not in existing_rule_cols:
            conn.execute("ALTER TABLE postprocess_rules ADD COLUMN output_filename TEXT NOT NULL DEFAULT 'postprocessed.md'")
            logger.info("Migration v8: added column 'output_filename' to postprocess_rules table")
        logger.info("Migration v8: completed postprocess schema migration")

    def _migrate_v9(self, conn):
        """V9: add default postprocess rule to callers table."""
        existing_caller_cols = {row[1] for row in conn.execute("PRAGMA table_info(callers)").fetchall()}
        if "default_postprocess_rule_id" not in existing_caller_cols:
            conn.execute("ALTER TABLE callers ADD COLUMN default_postprocess_rule_id TEXT")
            logger.info("Migration v9: added column 'default_postprocess_rule_id' to callers table")

    def _migrate_v10(self, conn):
        """V10: add postprocess rule snapshot fields to tasks table."""
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "postprocess_rule_title_snapshot" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_rule_title_snapshot TEXT")
            logger.info("Migration v10: added column 'postprocess_rule_title_snapshot' to tasks table")
        if "postprocess_prompt_snapshot" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN postprocess_prompt_snapshot TEXT")
            logger.info("Migration v10: added column 'postprocess_prompt_snapshot' to tasks table")

    def _migrate_v11(self, conn):
        """V11: postprocess 三层模型（action / plan / run），并迁移历史 rules 数据。

        迁移策略：每条 postprocess_rules 行生成同 ID 的 action 与同 ID 的单步 plan，
        使 tasks.postprocess_rule_id 与 callers.default_postprocess_rule_id 的既有引用
        无需改写即可解析到对应 plan。
        """
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS postprocess_actions (
                action_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'llm_transform',
                config TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_postprocess_actions_enabled ON postprocess_actions(enabled);

            CREATE TABLE IF NOT EXISTS postprocess_plans (
                plan_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                steps TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_postprocess_plans_enabled ON postprocess_plans(enabled);

            CREATE TABLE IF NOT EXISTS postprocess_runs (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                plan_id TEXT,
                plan_title_snapshot TEXT NOT NULL,
                steps_snapshot TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                current_step INTEGER NOT NULL DEFAULT 0,
                step_results TEXT,
                trigger_source TEXT NOT NULL DEFAULT 'manual',
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_pp_runs_task ON postprocess_runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_pp_runs_status ON postprocess_runs(status);
        """)

        rules = conn.execute("SELECT * FROM postprocess_rules").fetchall()
        for rule in rules:
            config = json.dumps(
                {
                    "prompt": rule["prompt"],
                    "output_filename": rule["output_filename"],
                    "context_size": None,
                },
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO postprocess_actions
                    (action_id, name, type, config, enabled, created_at, updated_at)
                VALUES (?, ?, 'llm_transform', ?, ?, ?, ?)
                """,
                (rule["rule_id"], rule["title"], config, rule["enabled"], rule["created_at"], rule["updated_at"]),
            )
            steps = json.dumps([{"action_id": rule["rule_id"], "output_filename": None}], ensure_ascii=False)
            conn.execute(
                """
                INSERT OR IGNORE INTO postprocess_plans
                    (plan_id, title, description, steps, enabled, created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (rule["rule_id"], rule["title"], steps, rule["enabled"], rule["created_at"], rule["updated_at"]),
            )
        if rules:
            logger.info(f"Migration v11: migrated {len(rules)} postprocess rules into actions/plans")
        logger.info("Migration v11: completed postprocess pipeline schema migration")
        
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
        caller_id: Optional[str] = None,
        enable_postprocess: bool = False,
        postprocess_rule_id: Optional[str] = None,
        postprocess_context_size: Optional[int] = None,
        postprocess_status: Optional[str] = None,
        postprocess_output_filename: Optional[str] = None,
        postprocess_rule_title_snapshot: Optional[str] = None,
        postprocess_prompt_snapshot: Optional[str] = None,
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
            caller_id: Caller identifier for control plane (optional).
            enable_postprocess: Whether to run postprocess after MinerU finishes.
            postprocess_rule_id: Rule ID selected for postprocess.
            postprocess_context_size: Context window size for postprocess.
            postprocess_status: Lifecycle for postprocess stage.
            postprocess_output_filename: Frozen artifact filename for this task.
            postprocess_rule_title_snapshot: Frozen rule title used by this task.
            postprocess_prompt_snapshot: Frozen prompt used by this task.
            **kwargs: Additional parameters.
        """
        effective_postprocess_status = postprocess_status or ("pending" if enable_postprocess else "not_enabled")
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    task_id, task_dir, input_filename, backend, lang,
                    formula_enable, table_enable, image_analysis,
                    start_page_id, end_page_id, server_url, timeout_seconds,
                    owner_id, owner_type, caller_id,
                    enable_postprocess, postprocess_rule_id, postprocess_context_size, postprocess_status,
                    postprocess_output_filename, postprocess_rule_title_snapshot, postprocess_prompt_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_dir, input_filename, backend, lang,
                int(formula_enable), int(table_enable), int(image_analysis),
                start_page_id, end_page_id, server_url, timeout_seconds,
                owner_id, owner_type, caller_id,
                int(enable_postprocess), postprocess_rule_id, postprocess_context_size, effective_postprocess_status,
                postprocess_output_filename, postprocess_rule_title_snapshot, postprocess_prompt_snapshot
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
    
    # ========== Caller Management ==========
    
    def create_caller(
        self,
        caller_id: str,
        name: str,
        api_key: str,
        api_key_prefix: str,
        api_key_suffix: str,
        default_postprocess_rule_id: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> None:
        """Create a new caller.
        
        Args:
            caller_id: Unique caller identifier.
            name: Caller display name.
            api_key: The API key (plaintext).
            api_key_prefix: First few characters for display.
            api_key_suffix: Last few characters for display.
            expires_at: Optional expiration timestamp (ISO format).
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO callers (
                    caller_id, name, api_key, api_key_prefix, api_key_suffix,
                    default_postprocess_rule_id, expires_at, disabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (caller_id, name, api_key, api_key_prefix, api_key_suffix, default_postprocess_rule_id, expires_at, now, now))
        
        logger.info(f"Caller created: {caller_id} ({name})")
    
    def get_caller(self, caller_id: str) -> Optional[Dict[str, Any]]:
        """Get caller by ID.
        
        Args:
            caller_id: Caller UUID.
            
        Returns:
            Caller data dict or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM callers WHERE caller_id = ?", 
                (caller_id,)
            ).fetchone()
            return dict(row) if row else None
    
    def get_caller_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get caller by API key.
        
        Args:
            api_key: The API key (plaintext).
            
        Returns:
            Caller data dict or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM callers WHERE api_key = ? AND disabled = 0", 
                (api_key,)
            ).fetchone()
            return dict(row) if row else None
    
    def list_callers(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """List all callers.
        
        Args:
            include_disabled: Whether to include disabled callers.
            
        Returns:
            List of caller dicts.
        """
        with self._conn() as conn:
            if include_disabled:
                rows = conn.execute("SELECT * FROM callers ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM callers WHERE disabled = 0 ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]
    
    def update_caller(
        self,
        caller_id: str,
        name: Optional[str] = None,
        disabled: Optional[bool] = None,
        default_postprocess_rule_id: Any = UNSET,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Update caller information.
        
        Args:
            caller_id: Caller UUID.
            name: New name (optional).
            disabled: New disabled status (optional).
            expires_at: New expiration timestamp (optional).
            
        Returns:
            True if updated, False if not found.
        """
        now = datetime.now().isoformat()
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if disabled is not None:
            updates.append("disabled = ?")
            params.append(int(disabled))
        if default_postprocess_rule_id is not UNSET:
            updates.append("default_postprocess_rule_id = ?")
            params.append(default_postprocess_rule_id)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(caller_id)
        
        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE callers SET {', '.join(updates)} WHERE caller_id = ?",
                tuple(params)
            )
            return cursor.rowcount > 0
    
    def reset_caller_key(
        self,
        caller_id: str,
        api_key: str,
        api_key_prefix: str,
        api_key_suffix: str,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Reset a caller's API key.
        
        Args:
            caller_id: Caller UUID.
            api_key: New API key (plaintext).
            api_key_prefix: New prefix for display.
            api_key_suffix: New suffix for display.
            expires_at: Optional new expiration timestamp. If not provided, keeps the existing expiration.
            
        Returns:
            True if reset, False if not found.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            # If expires_at is not provided, keep the existing one
            if expires_at is None:
                cursor = conn.execute("""
                    UPDATE callers 
                    SET api_key = ?, api_key_prefix = ?, api_key_suffix = ?, 
                        updated_at = ?
                    WHERE caller_id = ?
                """, (api_key, api_key_prefix, api_key_suffix, now, caller_id))
            else:
                cursor = conn.execute("""
                    UPDATE callers 
                    SET api_key = ?, api_key_prefix = ?, api_key_suffix = ?, 
                        expires_at = ?, updated_at = ?
                    WHERE caller_id = ?
                """, (api_key, api_key_prefix, api_key_suffix, expires_at, now, caller_id))
            return cursor.rowcount > 0
    
    def update_caller_last_used(self, caller_id: str) -> None:
        """Update the last used timestamp for a caller.
        
        Args:
            caller_id: Caller UUID.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE callers SET last_used_at = ?, updated_at = ? WHERE caller_id = ?",
                (now, now, caller_id)
            )
    
    def delete_caller(self, caller_id: str) -> bool:
        """Delete a caller.
        
        Args:
            caller_id: Caller UUID.
            
        Returns:
            True if deleted, False if not found.
        """
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM callers WHERE caller_id = ?", (caller_id,))
            return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its logs.
        
        Args:
            task_id: Task UUID.
            
        Returns:
            True if deleted, False if not found.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))
            cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            return cursor.rowcount > 0

    # ========== Postprocess Action Management ==========

    def create_postprocess_action(
        self,
        action_id: str,
        name: str,
        type: str = "llm_transform",
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> None:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO postprocess_actions (action_id, name, type, config, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (action_id, name, type, json.dumps(config or {}, ensure_ascii=False), int(enabled), now, now),
            )

    def list_postprocess_actions(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if include_disabled:
                rows = conn.execute("SELECT * FROM postprocess_actions ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM postprocess_actions WHERE enabled = 1 ORDER BY created_at DESC").fetchall()
            return [self._decode_action_row(row) for row in rows]

    def get_postprocess_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM postprocess_actions WHERE action_id = ?", (action_id,)).fetchone()
            return self._decode_action_row(row) if row else None

    def update_postprocess_action(
        self,
        action_id: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        enabled: Optional[bool] = None,
    ) -> bool:
        updates = []
        params: list = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if config is not None:
            updates.append("config = ?")
            params.append(json.dumps(config, ensure_ascii=False))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(int(enabled))
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(action_id)
        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE postprocess_actions SET {', '.join(updates)} WHERE action_id = ?",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_postprocess_action(self, action_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM postprocess_actions WHERE action_id = ?", (action_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _decode_action_row(row) -> Dict[str, Any]:
        item = dict(row)
        try:
            item["config"] = json.loads(item.get("config") or "{}")
        except json.JSONDecodeError:
            item["config"] = {}
        return item

    # ========== Postprocess Plan Management ==========

    def create_postprocess_plan(
        self,
        plan_id: str,
        title: str,
        steps: List[Dict[str, Any]],
        description: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO postprocess_plans (plan_id, title, description, steps, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (plan_id, title, description, json.dumps(steps, ensure_ascii=False), int(enabled), now, now),
            )

    def list_postprocess_plans(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if include_disabled:
                rows = conn.execute("SELECT * FROM postprocess_plans ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM postprocess_plans WHERE enabled = 1 ORDER BY created_at DESC").fetchall()
            return [self._decode_plan_row(row) for row in rows]

    def get_postprocess_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM postprocess_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            return self._decode_plan_row(row) if row else None

    def update_postprocess_plan(
        self,
        plan_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        enabled: Optional[bool] = None,
    ) -> bool:
        updates = []
        params: list = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if steps is not None:
            updates.append("steps = ?")
            params.append(json.dumps(steps, ensure_ascii=False))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(int(enabled))
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(plan_id)
        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE postprocess_plans SET {', '.join(updates)} WHERE plan_id = ?",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_postprocess_plan(self, plan_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM postprocess_plans WHERE plan_id = ?", (plan_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _decode_plan_row(row) -> Dict[str, Any]:
        item = dict(row)
        try:
            item["steps"] = json.loads(item.get("steps") or "[]")
        except json.JSONDecodeError:
            item["steps"] = []
        return item

    # ========== Postprocess Run Management ==========
    # run 状态枚举: pending / running / completed / failed / cancelled

    def create_postprocess_run(
        self,
        run_id: str,
        task_id: str,
        plan_id: Optional[str],
        plan_title_snapshot: str,
        steps_snapshot: List[Dict[str, Any]],
        trigger_source: str = "manual",
    ) -> None:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO postprocess_runs (
                    run_id, task_id, plan_id, plan_title_snapshot, steps_snapshot,
                    status, current_step, trigger_source, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (
                    run_id, task_id, plan_id, plan_title_snapshot,
                    json.dumps(steps_snapshot, ensure_ascii=False), trigger_source, now,
                ),
            )

    def get_postprocess_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM postprocess_runs WHERE run_id = ?", (run_id,)).fetchone()
            return self._decode_run_row(row) if row else None

    def list_postprocess_runs(
        self,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM postprocess_runs"
        conditions = []
        params: list = []
        if task_id is not None:
            conditions.append("task_id = ?")
            params.append(task_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._decode_run_row(row) for row in rows]

    def get_latest_postprocess_run(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM postprocess_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            return self._decode_run_row(row) if row else None

    def claim_postprocess_run(self, run_id: str) -> bool:
        """CAS: pending → running。返回是否成功认领。"""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE postprocess_runs SET status = 'running', started_at = ?
                WHERE run_id = ? AND status = 'pending'
                """,
                (now, run_id),
            )
            return cursor.rowcount > 0

    def update_postprocess_run_steps(
        self,
        run_id: str,
        current_step: int,
        step_results: List[Dict[str, Any]],
    ) -> bool:
        """推进步骤进度（仅在 running 状态下生效，防止迟写覆盖终态）。"""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE postprocess_runs SET current_step = ?, step_results = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (current_step, json.dumps(step_results, ensure_ascii=False), run_id),
            )
            return cursor.rowcount > 0

    def finish_postprocess_run(self, run_id: str, status: str, error: Optional[str] = None) -> bool:
        """CAS: running → 终态（completed / failed / cancelled）。"""
        if status not in ("completed", "failed", "cancelled"):
            raise ValueError(f"Invalid terminal run status: {status}")
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE postprocess_runs SET status = ?, error = ?, finished_at = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (status, error, now, run_id),
            )
            return cursor.rowcount > 0

    def cancel_pending_postprocess_run(self, run_id: str) -> bool:
        """CAS: pending → cancelled（尚未被 runner 认领的 run）。"""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE postprocess_runs SET status = 'cancelled', finished_at = ?
                WHERE run_id = ? AND status = 'pending'
                """,
                (now, run_id),
            )
            return cursor.rowcount > 0

    def reset_running_postprocess_runs(self) -> int:
        """启动恢复：running → pending，等待 runner 重新认领（幂等覆盖重跑）。"""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE postprocess_runs SET status = 'pending', started_at = NULL
                WHERE status = 'running'
                """
            )
            return cursor.rowcount

    @staticmethod
    def _decode_run_row(row) -> Dict[str, Any]:
        item = dict(row)
        for field_name in ("steps_snapshot", "step_results"):
            fallback = [] if field_name == "steps_snapshot" else None
            raw = item.get(field_name)
            if raw is None:
                item[field_name] = fallback
                continue
            try:
                item[field_name] = json.loads(raw)
            except json.JSONDecodeError:
                item[field_name] = fallback
        return item

    # ========== Admin Credentials Management ==========
    
    def create_admin(self, username: str, password_hash: str, must_change_password: bool = False) -> None:
        """Create or reset admin credentials.
        
        Args:
            username: Admin username.
            password_hash: Hash of the password.
            must_change_password: Whether the admin must change password on first login.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO admin_credentials (
                    username, password_hash, must_change_password, 
                    password_changed_at, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, ?, ?)
            """, (username, password_hash, int(must_change_password), now, now))
        
        logger.info(f"Admin credentials created/updated for: {username}")
    
    def get_admin(self, username: str) -> Optional[Dict[str, Any]]:
        """Get admin credentials.
        
        Args:
            username: Admin username.
            
        Returns:
            Admin data dict or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM admin_credentials WHERE username = ?", 
                (username,)
            ).fetchone()
            return dict(row) if row else None
    
    def update_admin_password(
        self,
        username: str,
        password_hash: str,
    ) -> bool:
        """Update admin password.
        
        Args:
            username: Admin username.
            password_hash: New password hash.
            
        Returns:
            True if updated, False if not found.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE admin_credentials 
                SET password_hash = ?, must_change_password = 0, 
                    password_changed_at = ?, updated_at = ?
                WHERE username = ?
            """, (password_hash, now, now, username))
            return cursor.rowcount > 0

    def set_admin_password_change_required(self, username: str, required: bool) -> bool:
        """Update whether an admin must change password.
        
        Args:
            username: Admin username.
            required: Whether password change is required.
            
        Returns:
            True if updated, False if not found.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE admin_credentials
                SET must_change_password = ?, updated_at = ?
                WHERE username = ?
            """, (int(required), now, username))
            return cursor.rowcount > 0
    
    def admin_needs_password_change(self, username: str) -> bool:
        """Check if admin needs to change password.
        
        Args:
            username: Admin username.
            
        Returns:
            True if password change is required.
        """
        admin = self.get_admin(username)
        if not admin:
            return True  # If admin doesn't exist, needs to be created
        return bool(admin.get("must_change_password", 0) == 1)
