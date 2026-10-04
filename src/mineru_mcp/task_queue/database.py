"""Task Database Module

SQLite-based task storage with WAL mode for better concurrency.
"""

import json
import sqlite3
import shutil
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from loguru import logger


UNSET = object()


class TaskDatabase:
    """SQLite database for task queue management."""
    
    SCHEMA_VERSION = 18

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

                    -- File content fingerprint (sha256) for dedup
                    file_hash TEXT,
                    file_size INTEGER,

                    -- Dedup reuse source (internal audit only, not exposed to clients)
                    dedup_source_task_id TEXT,

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

                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL DEFAULT 'string',
                    updated_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS system_secrets (
                    key TEXT PRIMARY KEY,
                    secret_encrypted TEXT NOT NULL,
                    secret_key_id TEXT NOT NULL,
                    secret_prefix TEXT NOT NULL,
                    secret_suffix TEXT NOT NULL,
                    updated_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

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

            if current_version < 12:
                logger.info(f"Running schema migration v11 -> v12")
                self._migrate_v12(conn)
                conn.execute(f"PRAGMA user_version = 12")
                current_version = 12

            if current_version < 13:
                logger.info(f"Running schema migration v12 -> v13")
                self._migrate_v13(conn)
                conn.execute(f"PRAGMA user_version = 13")
                current_version = 13

            if current_version < 14:
                logger.info(f"Running schema migration v13 -> v14")
                self._migrate_v14(conn)
                conn.execute(f"PRAGMA user_version = 14")
                current_version = 14

            if current_version < 15:
                logger.info(f"Running schema migration v14 -> v15")
                self._migrate_v15(conn)
                conn.execute(f"PRAGMA user_version = 15")
                current_version = 15

            if current_version < 16:
                logger.info(f"Running schema migration v15 -> v16")
                self._migrate_v16(conn)
                conn.execute(f"PRAGMA user_version = 16")
                current_version = 16

            if current_version < 17:
                logger.info(f"Running schema migration v16 -> v17")
                self._migrate_v17(conn)
                conn.execute(f"PRAGMA user_version = 17")
                current_version = 17

            if current_version < 18:
                logger.info("Running schema migration v17 -> v18")
                self._migrate_v18(conn)
                conn.execute("PRAGMA user_version = 18")
                current_version = 18

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
                locale TEXT DEFAULT '',
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

    def _migrate_v12(self, conn):
        """V12: add locale column to admin_credentials for UI language preference."""
        existing_admin_cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_credentials)").fetchall()}
        if "locale" not in existing_admin_cols:
            conn.execute("ALTER TABLE admin_credentials ADD COLUMN locale TEXT DEFAULT ''")
            logger.info("Migration v12: added column 'locale' to admin_credentials table")

    def _migrate_v13(self, conn):
        """V13: migrate caller API keys from plaintext to encrypted storage."""
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(callers)").fetchall()}
        if "api_key_encrypted" in existing_cols:
            self._ensure_caller_key_indexes(conn)
            return

        if "api_key" not in existing_cols:
            self._ensure_caller_key_indexes(conn)
            return

        rows = conn.execute(
            """
            SELECT caller_id, name, api_key, api_key_prefix, api_key_suffix,
                   default_postprocess_rule_id, expires_at, disabled, last_used_at,
                   created_at, updated_at
            FROM callers
            """
        ).fetchall()

        master_key = None
        if rows:
            from mineru_mcp.config import require_caller_key_master_key

            master_key = require_caller_key_master_key()

        conn.executescript(
            """
            DROP INDEX IF EXISTS idx_callers_api_key;
            DROP INDEX IF EXISTS idx_callers_api_key_hash;

            CREATE TABLE callers_new (
                caller_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key_encrypted TEXT NOT NULL,
                api_key_hash TEXT NOT NULL,
                api_key_key_id TEXT NOT NULL,
                api_key_prefix TEXT NOT NULL,
                api_key_suffix TEXT NOT NULL,
                default_postprocess_rule_id TEXT,
                expires_at TIMESTAMP,
                disabled INTEGER NOT NULL DEFAULT 0,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        if rows and master_key:
            from mineru_mcp.caller_key_crypto import encrypt_api_key

            for row in rows:
                encrypted = encrypt_api_key(row["api_key"], master_key)
                conn.execute(
                    """
                    INSERT INTO callers_new (
                        caller_id, name, api_key_encrypted, api_key_hash, api_key_key_id,
                        api_key_prefix, api_key_suffix, default_postprocess_rule_id,
                        expires_at, disabled, last_used_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["caller_id"],
                        row["name"],
                        encrypted.ciphertext,
                        encrypted.digest,
                        encrypted.key_id,
                        encrypted.prefix,
                        encrypted.suffix,
                        row["default_postprocess_rule_id"],
                        row["expires_at"],
                        row["disabled"],
                        row["last_used_at"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

        conn.executescript(
            """
            DROP TABLE callers;
            ALTER TABLE callers_new RENAME TO callers;
            """
        )
        self._ensure_caller_key_indexes(conn)
        logger.info("Migration v13: migrated caller API keys to encrypted storage")

    def _ensure_caller_key_indexes(self, conn):
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_callers_name ON callers(name);
            CREATE INDEX IF NOT EXISTS idx_callers_disabled ON callers(disabled);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_callers_api_key_hash ON callers(api_key_hash);
            """
        )

    def _migrate_v14(self, conn):
        """V14: add system settings and encrypted system secrets."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                updated_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS system_secrets (
                key TEXT PRIMARY KEY,
                secret_encrypted TEXT NOT NULL,
                secret_key_id TEXT NOT NULL,
                secret_prefix TEXT NOT NULL,
                secret_suffix TEXT NOT NULL,
                updated_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        logger.info("Migration v14: added system_settings and system_secrets tables")

    def _migrate_v15(self, conn):
        """V15: add file_hash and file_size columns to tasks for content dedup."""
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

        if "file_hash" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN file_hash TEXT")
            logger.info("Migration v15: added column 'file_hash' to tasks table")

        if "file_size" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN file_size INTEGER")
            logger.info("Migration v15: added column 'file_size' to tasks table")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_file_hash ON tasks(file_hash)")
        logger.info("Migration v15: added idx_tasks_file_hash index")

    def _migrate_v16(self, conn):
        """V16: add dedup_source_task_id column to tasks for dedup audit trail."""
        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

        if "dedup_source_task_id" not in existing_tasks_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN dedup_source_task_id TEXT")
            logger.info("Migration v16: added column 'dedup_source_task_id' to tasks table")

    def _migrate_v17(self, conn):
        """V17：增加 caller 页数额度、配额流水及任务计费字段。"""
        caller_table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'callers'"
        ).fetchone()
        if caller_table_exists is None:
            conn.execute(
                """
                CREATE TABLE callers (
                    caller_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    api_key_key_id TEXT NOT NULL,
                    api_key_prefix TEXT NOT NULL,
                    api_key_suffix TEXT NOT NULL,
                    default_postprocess_rule_id TEXT,
                    expires_at TIMESTAMP,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_caller_key_indexes(conn)

        existing_caller_cols = {row[1] for row in conn.execute("PRAGMA table_info(callers)").fetchall()}
        if "quota_total_pages" not in existing_caller_cols:
            conn.execute("ALTER TABLE callers ADD COLUMN quota_total_pages INTEGER")

        existing_tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        task_columns = (
            ("pages_reserved", "INTEGER"),
            ("pages_billed", "INTEGER"),
            ("quota_released", "INTEGER DEFAULT 0"),
        )
        for column, definition in task_columns:
            if column not in existing_tasks_cols:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quota_ledger (
                ledger_id TEXT PRIMARY KEY,
                caller_id TEXT NOT NULL,
                task_id TEXT,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                balance_after INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_quota_ledger_caller_created
                ON quota_ledger(caller_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_quota_ledger_task_id
                ON quota_ledger(task_id);
            """
        )
        logger.info("Migration v17: added caller quotas, quota ledger, and task accounting fields")

    def _migrate_v18(self, conn):
        """V18：新增用户账号，并将新账号关联到唯一 caller。"""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                disabled INTEGER NOT NULL DEFAULT 0,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        existing_caller_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(callers)").fetchall()
        }
        if "user_id" not in existing_caller_cols:
            conn.execute("ALTER TABLE callers ADD COLUMN user_id TEXT")

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_callers_user_id
            ON callers(user_id) WHERE user_id IS NOT NULL
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role_disabled ON users(role, disabled)")

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
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        pages_reserved: Optional[int] = None,
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
            file_hash: SHA-256 hex digest of the input file content.
            file_size: Input file size in bytes.
            pages_reserved: 任务预扣的解析页数。
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
                    postprocess_output_filename, postprocess_rule_title_snapshot, postprocess_prompt_snapshot,
                    file_hash, file_size, pages_reserved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_dir, input_filename, backend, lang,
                int(formula_enable), int(table_enable), int(image_analysis),
                start_page_id, end_page_id, server_url, timeout_seconds,
                owner_id, owner_type, caller_id,
                int(enable_postprocess), postprocess_rule_id, postprocess_context_size, effective_postprocess_status,
                postprocess_output_filename, postprocess_rule_title_snapshot, postprocess_prompt_snapshot,
                file_hash, file_size, pages_reserved
            ))
            
        logger.info(f"Task created: {task_id} (owner={owner_id})")

    # ========== Dedup helpers ==========

    def build_dedup_key(
        self,
        *,
        file_hash: Optional[str],
        backend: str,
        lang: str,
        start_page_id: int,
        end_page_id: int,
        formula_enable: bool,
        table_enable: bool,
        image_analysis: bool,
        server_url: Optional[str],
    ) -> Optional[str]:
        """Build the dedup key for a task.

        去重键 = 文件内容 hash + 全部影响解析结果的参数。后处理参数不进去重键
        （复用的是解析产物，后处理 run 各任务独立执行）。

        file_hash 为 None（历史任务/未落库）时返回 None，表示该任务无去重能力。
        """
        if not file_hash:
            return None
        return "|".join([
            file_hash,
            backend,
            lang,
            str(int(start_page_id)),
            str(int(end_page_id)),
            "1" if formula_enable else "0",
            "1" if table_enable else "0",
            "1" if image_analysis else "0",
            server_url or "",
        ])

    def dedup_key_for_task(self, task: Dict[str, Any]) -> Optional[str]:
        """从任务行构建去重键（调度去重判断用）。"""
        return self.build_dedup_key(
            file_hash=task.get("file_hash"),
            backend=task.get("backend") or "",
            lang=task.get("lang") or "ch",
            start_page_id=task.get("start_page_id") or 0,
            end_page_id=task.get("end_page_id") or 99999,
            formula_enable=bool(task.get("formula_enable", 1)),
            table_enable=bool(task.get("table_enable", 1)),
            image_analysis=bool(task.get("image_analysis", 1)),
            server_url=task.get("server_url"),
        )

    def find_dedup_source(self, dedup_key: str, exclude_task_id: str) -> Optional[Dict[str, Any]]:
        """查找同去重键的 completed 任务作为复用源（排除自身）。

        仅返回已完成且未复用其他任务的任务；复用源的产物有效性由调用方校验。
        """
        with self._conn() as conn:
            # 不能以 completed 任务作为 key 列直接匹配——key 是计算值，这里按字段反查。
            # 为保持简洁与索引利用，先按 file_hash 粗筛再在内存中精确匹配 key。
            # 取最近完成的：cleanup 会物理删目录，最新完成的最可能在盘上。
            task_hash = dedup_key.split("|")[0]
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'completed' AND file_hash = ? AND task_id != ?
                ORDER BY completed_at DESC
                """,
                (task_hash, exclude_task_id),
            ).fetchall()

        for row in rows:
            task = dict(row)
            if self.dedup_key_for_task(task) == dedup_key:
                return task
        return None

    def find_active_dedup_peer(self, dedup_key: str, exclude_task_id: str) -> Optional[Dict[str, Any]]:
        """查找同去重键、正在解析的任务（排除自身）。

        存在即说明该键已在解析中，本任务应保持 pending 等待，避免并发解析同一文件。
        仅查 processing：pending 任务尚未被领取，不算 active；同批内的并发由
        scheduler 的 `claimed_keys` 集合防护。
        """
        with self._conn() as conn:
            task_hash = dedup_key.split("|")[0]
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'processing' AND file_hash = ? AND task_id != ?
                ORDER BY created_at ASC
                """,
                (task_hash, exclude_task_id),
            ).fetchall()

        for row in rows:
            task = dict(row)
            if self.dedup_key_for_task(task) == dedup_key:
                return task
        return None

    def mark_dedup_completed(self, task_id: str, source_task_id: str) -> bool:
        """将任务标记为 completed，并记录复用来源（去重完成路径）。

        返回 True 表示成功更新。
        """
        now = datetime.now().isoformat()
        message = f"Reused parsing result from task {source_task_id}"
        updated = self.execute(
            """
            UPDATE tasks
            SET status = 'completed', progress = 100,
                message = ?, completed_at = ?, updated_at = ?, dedup_source_task_id = ?
            WHERE task_id = ? AND status = 'pending'
            """,
            (message, now, now, source_task_id, task_id),
        )
        if updated > 0:
            logger.info(f"Task {task_id} completed via dedup from {source_task_id}")
            return True
        return False
        
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
        if status in ("completed", "failed", "cancelled"):
            from mineru_mcp.services.quota_service import QuotaService

            quota_service = QuotaService(self)
            task = self.get_task(task_id)
            if status == "completed":
                actual_pages = quota_service.actual_pages_from_task(task)
                if actual_pages is None and task is not None:
                    actual_pages = task.get("pages_reserved")
                quota_service.settle(
                    task.get("caller_id") if task else None,
                    task_id,
                    actual_pages,
                )
            else:
                quota_service.release(task.get("caller_id") if task else None, task_id)
        
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

    @staticmethod
    def _quota_balance_in_transaction(conn, caller_id: str) -> Optional[int]:
        """读取有限额度的当前余额；不限量调用方返回 None。"""
        caller = conn.execute(
            "SELECT quota_total_pages FROM callers WHERE caller_id = ?",
            (caller_id,),
        ).fetchone()
        if caller is None or caller["quota_total_pages"] is None:
            return None

        latest = conn.execute(
            "SELECT balance_after FROM quota_ledger WHERE caller_id = ? ORDER BY rowid DESC LIMIT 1",
            (caller_id,),
        ).fetchone()
        if latest is not None and latest["balance_after"] is not None:
            return int(latest["balance_after"])
        return int(caller["quota_total_pages"])

    def get_quota_balance(self, caller_id: Optional[str]) -> Optional[int]:
        """返回 caller 当前剩余页数；无 caller 或不限量 caller 返回 None。"""
        if not caller_id:
            return None
        with self._conn() as conn:
            return self._quota_balance_in_transaction(conn, caller_id)

    def reserve_quota_pages(self, caller_id: Optional[str], task_id: str, pages: int) -> tuple[bool, Optional[int]]:
        """原子检查并预扣页数，返回 (是否成功, 预扣后的余额)。"""
        pages = int(pages)
        if pages < 0:
            raise ValueError("预扣页数不能为负数")
        if not caller_id:
            return True, None

        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            caller = conn.execute(
                "SELECT quota_total_pages FROM callers WHERE caller_id = ?",
                (caller_id,),
            ).fetchone()
            if caller is None or caller["quota_total_pages"] is None:
                return True, None

            existing = conn.execute(
                """
                SELECT 1 FROM quota_ledger
                WHERE caller_id = ? AND task_id = ? AND reason = 'task_reservation'
                LIMIT 1
                """,
                (caller_id, task_id),
            ).fetchone()
            balance = self._quota_balance_in_transaction(conn, caller_id)
            if existing is not None:
                return True, balance
            if balance is None:
                return True, None
            if balance < pages:
                return False, balance

            if pages:
                conn.execute(
                    """
                    INSERT INTO quota_ledger
                        (ledger_id, caller_id, task_id, delta, reason, balance_after, created_at)
                    VALUES (?, ?, ?, ?, 'task_reservation', ?, ?)
                    """,
                    (
                        secrets.token_hex(8),
                        caller_id,
                        task_id,
                        -pages,
                        balance - pages,
                        datetime.now().isoformat(),
                    ),
                )
                balance -= pages
            return True, balance

    def settle_quota_pages(
        self,
        caller_id: Optional[str],
        task_id: str,
        actual_pages: Optional[int],
    ) -> Optional[int]:
        """按真实页数结算，写入计费页数并调整预扣余额。"""
        if actual_pages is not None and int(actual_pages) < 0:
            raise ValueError("实际页数不能为负数")

        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute(
                """
                SELECT caller_id, pages_reserved, pages_billed, quota_released
                FROM tasks WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is None:
                return None
            if task["pages_billed"] is not None:
                return int(task["pages_billed"])
            if task["quota_released"]:
                return None

            effective_caller_id = task["caller_id"] or caller_id
            reservation = None
            if effective_caller_id:
                reservation = conn.execute(
                    """
                    SELECT delta FROM quota_ledger
                    WHERE caller_id = ? AND task_id = ? AND reason = 'task_reservation'
                    LIMIT 1
                    """,
                    (effective_caller_id, task_id),
                ).fetchone()

            reserved = task["pages_reserved"]
            if reserved is None and reservation is not None:
                reserved = -int(reservation["delta"])
            reserved = int(reserved or 0)
            billed = reserved if actual_pages is None else int(actual_pages)

            adjustment = reserved - billed if reservation is not None else 0
            if adjustment:
                balance = self._quota_balance_in_transaction(conn, effective_caller_id)
                balance_after = balance + adjustment if balance is not None else None
                conn.execute(
                    """
                    INSERT INTO quota_ledger
                        (ledger_id, caller_id, task_id, delta, reason, balance_after, created_at)
                    VALUES (?, ?, ?, ?, 'task_settlement_adjustment', ?, ?)
                    """,
                    (
                        secrets.token_hex(8),
                        effective_caller_id,
                        task_id,
                        adjustment,
                        balance_after,
                        datetime.now().isoformat(),
                    ),
                )

            conn.execute(
                "UPDATE tasks SET pages_billed = ? WHERE task_id = ?",
                (billed, task_id),
            )
            return billed

    def release_quota_pages(self, caller_id: Optional[str], task_id: str) -> bool:
        """幂等返还预扣额度；也支持任务行创建失败后的预扣补偿。"""
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute(
                """
                SELECT caller_id, pages_reserved, pages_billed, quota_released
                FROM tasks WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is not None and (task["quota_released"] or task["pages_billed"] is not None):
                return False

            effective_caller_id = (task["caller_id"] if task is not None else None) or caller_id
            if not effective_caller_id:
                return False
            reservation = conn.execute(
                """
                SELECT delta FROM quota_ledger
                WHERE caller_id = ? AND task_id = ? AND reason = 'task_reservation'
                LIMIT 1
                """,
                (effective_caller_id, task_id),
            ).fetchone()
            if task is None and reservation is None:
                return False

            if task is None:
                already_released = conn.execute(
                    """
                    SELECT 1 FROM quota_ledger
                    WHERE caller_id = ? AND task_id = ? AND reason = 'task_release'
                    LIMIT 1
                    """,
                    (effective_caller_id, task_id),
                ).fetchone()
                if already_released is not None:
                    return False
                reserved = -int(reservation["delta"])
            else:
                reserved = task["pages_reserved"]
                if reserved is None and reservation is not None:
                    reserved = -int(reservation["delta"])
                reserved = int(reserved or 0)
                conn.execute(
                    "UPDATE tasks SET quota_released = 1 WHERE task_id = ? AND quota_released = 0",
                    (task_id,),
                )

            if reservation is None or reserved <= 0:
                return task is not None

            balance = self._quota_balance_in_transaction(conn, effective_caller_id)
            balance_after = balance + reserved if balance is not None else None
            conn.execute(
                """
                INSERT INTO quota_ledger
                    (ledger_id, caller_id, task_id, delta, reason, balance_after, created_at)
                VALUES (?, ?, ?, ?, 'task_release', ?, ?)
                """,
                (
                    secrets.token_hex(8),
                    effective_caller_id,
                    task_id,
                    reserved,
                    balance_after,
                    datetime.now().isoformat(),
                ),
            )
            return True

    def top_up_quota_pages(self, caller_id: str, pages: int, reason: str) -> Dict[str, Any]:
        """累计增加预充值总量并追加一条入账流水。"""
        pages = int(pages)
        reason = (reason or "").strip()
        if pages <= 0:
            raise ValueError("充值页数必须大于零")
        if not reason:
            raise ValueError("充值原因不能为空")

        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            caller = conn.execute(
                "SELECT quota_total_pages FROM callers WHERE caller_id = ?",
                (caller_id,),
            ).fetchone()
            if caller is None:
                raise ValueError(f"Caller '{caller_id}' does not exist")

            balance = self._quota_balance_in_transaction(conn, caller_id)
            total_pages = int(caller["quota_total_pages"] or 0) + pages
            balance_after = pages if balance is None else balance + pages
            ledger_id = secrets.token_hex(8)
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE callers SET quota_total_pages = ?, updated_at = ? WHERE caller_id = ?",
                (total_pages, now, caller_id),
            )
            conn.execute(
                """
                INSERT INTO quota_ledger
                    (ledger_id, caller_id, task_id, delta, reason, balance_after, created_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (ledger_id, caller_id, pages, reason, balance_after, now),
            )
            return {
                "ledger_id": ledger_id,
                "caller_id": caller_id,
                "delta": pages,
                "quota_total_pages": total_pages,
                "balance_after": balance_after,
                "reason": reason,
                "created_at": now,
            }

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
        """Clean up old completed/failed tasks and their output directories.
        
        Args:
            days: Days to keep (delete older than this).
            
        Returns:
            Number of tasks deleted.
        """
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        with self._conn() as conn:
            # Get old tasks
            old_tasks = [
                dict(row)
                for row in conn.execute("""
                    SELECT task_id, task_dir FROM tasks
                    WHERE status IN ('completed', 'failed', 'cancelled')
                    AND completed_at < ?
                """, (cutoff_str,)).fetchall()
            ]
            
            # Delete from database
            conn.execute("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            """, (cutoff_str,))
            
            # Delete logs
            for task in old_tasks:
                conn.execute("DELETE FROM task_logs WHERE task_id = ?", (task['task_id'],))
                conn.execute("DELETE FROM postprocess_runs WHERE task_id = ?", (task['task_id'],))

        for task in old_tasks:
            task_dir = task.get("task_dir")
            if not task_dir:
                continue
            try:
                shutil.rmtree(task_dir, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"Failed to remove old task directory {task_dir}: {exc}")
                
        deleted_count = len(old_tasks)
        logger.info(f"Cleaned up {deleted_count} old tasks")
        return deleted_count

    # ========== System Settings Management ==========

    def list_system_settings(self) -> Dict[str, Dict[str, Any]]:
        """Return all system settings keyed by setting name."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM system_settings").fetchall()
            return {row["key"]: dict(row) for row in rows}

    def get_system_setting(self, key: str) -> Optional[Dict[str, Any]]:
        """Return one system setting by key."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM system_settings WHERE key = ?", (key,)).fetchone()
            return dict(row) if row else None

    def set_system_setting(
        self,
        *,
        key: str,
        value: str,
        value_type: str = "string",
        updated_by: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> None:
        """Create or update one non-secret system setting."""
        now = updated_at or datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO system_settings (key, value, value_type, updated_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    value_type = excluded.value_type,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (key, value, value_type, updated_by, now, now),
            )

    def delete_system_setting(self, key: str) -> bool:
        """Delete one system setting."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM system_settings WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def list_system_secrets(self, include_ciphertext: bool = False) -> Dict[str, Dict[str, Any]]:
        """Return all system secret metadata keyed by secret name."""
        fields = """
            key, secret_key_id, secret_prefix, secret_suffix,
            updated_by, created_at, updated_at
        """
        if include_ciphertext:
            fields = "key, secret_encrypted, secret_key_id, secret_prefix, secret_suffix, updated_by, created_at, updated_at"
        with self._conn() as conn:
            rows = conn.execute(f"SELECT {fields} FROM system_secrets").fetchall()
            return {row["key"]: dict(row) for row in rows}

    def set_system_secret(
        self,
        *,
        key: str,
        secret_encrypted: str,
        secret_key_id: str,
        secret_prefix: str,
        secret_suffix: str,
        updated_by: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> None:
        """Create or update one encrypted system secret."""
        now = updated_at or datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO system_secrets (
                    key, secret_encrypted, secret_key_id, secret_prefix, secret_suffix,
                    updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    secret_encrypted = excluded.secret_encrypted,
                    secret_key_id = excluded.secret_key_id,
                    secret_prefix = excluded.secret_prefix,
                    secret_suffix = excluded.secret_suffix,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    secret_encrypted,
                    secret_key_id,
                    secret_prefix,
                    secret_suffix,
                    updated_by,
                    now,
                    now,
                ),
            )

    def delete_system_secret(self, key: str) -> bool:
        """Delete one encrypted system secret."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM system_secrets WHERE key = ?", (key,))
            return cursor.rowcount > 0
    
    # ========== Caller Management ==========
    
    @staticmethod
    def _insert_caller(
        conn,
        caller_id: str,
        name: str,
        encrypted,
        default_postprocess_rule_id: Optional[str],
        expires_at: Optional[str],
        now: str,
        user_id: Optional[str] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO callers (
                caller_id, name, api_key_encrypted, api_key_hash, api_key_key_id,
                api_key_prefix, api_key_suffix, default_postprocess_rule_id,
                expires_at, disabled, created_at, updated_at, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                caller_id,
                name,
                encrypted.ciphertext,
                encrypted.digest,
                encrypted.key_id,
                encrypted.prefix,
                encrypted.suffix,
                default_postprocess_rule_id,
                expires_at,
                now,
                now,
                user_id,
            ),
        )

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
            api_key: The API key (plaintext, encrypted before storage).
            api_key_prefix: First few characters for display.
            api_key_suffix: Last few characters for display.
            expires_at: Optional expiration timestamp (ISO format).
        """
        from mineru_mcp.config import require_caller_key_master_key
        from mineru_mcp.caller_key_crypto import encrypt_api_key

        encrypted = encrypt_api_key(api_key, require_caller_key_master_key())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            self._insert_caller(
                conn,
                caller_id,
                name,
                encrypted,
                default_postprocess_rule_id,
                expires_at,
                now,
            )
        
        logger.info(f"Caller created: {caller_id} ({name})")

    def create_user_with_caller(
        self,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        caller_id: str,
        api_key: str,
    ) -> None:
        """在同一事务中创建用户和其唯一 caller/API key。"""
        from mineru_mcp.config import require_caller_key_master_key
        from mineru_mcp.caller_key_crypto import encrypt_api_key

        if role not in {"user", "admin"}:
            raise ValueError("用户角色无效")
        encrypted = encrypt_api_key(api_key, require_caller_key_master_key())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    user_id, username, password_hash, display_name, role,
                    disabled, must_change_password, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (user_id, username, password_hash, display_name, role, now, now),
            )
            self._insert_caller(
                conn,
                caller_id,
                display_name,
                encrypted,
                None,
                None,
                now,
                user_id,
            )
        logger.info(f"User created: {user_id} ({username})")

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """按用户名读取账号凭据。"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 读取用户资料。"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_caller(self, user_id: str) -> Optional[Dict[str, Any]]:
        """读取用户绑定的 caller 和配额摘要。"""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT c.caller_id, c.name, c.api_key_prefix, c.api_key_suffix,
                       c.disabled AS caller_disabled, c.quota_total_pages,
                       c.created_at, c.updated_at
                FROM callers c
                WHERE c.user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_users(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """列出用户及其关联 caller 的非敏感资料。"""
        query = """
            SELECT u.user_id, u.username, u.display_name, u.role, u.disabled,
                   u.must_change_password, u.created_at, u.updated_at,
                   c.caller_id, c.api_key_prefix, c.api_key_suffix,
                   c.quota_total_pages, c.disabled AS caller_disabled
            FROM users u
            LEFT JOIN callers c ON c.user_id = u.user_id
        """
        if not include_disabled:
            query += " WHERE u.disabled = 0"
        query += " ORDER BY u.created_at DESC"
        return self.fetch_all(query)

    def update_user(
        self,
        user_id: str,
        *,
        display_name: Optional[str] = None,
        disabled: Optional[bool] = None,
        role: Optional[str] = None,
        password_hash: Optional[str] = None,
        must_change_password: Optional[bool] = None,
    ) -> bool:
        """更新用户资料；禁用状态同步到其 API caller。"""
        if role is not None and role not in {"user", "admin"}:
            raise ValueError("用户角色无效")
        now = datetime.now().isoformat()
        updates = []
        params: list[Any] = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if disabled is not None:
            updates.append("disabled = ?")
            params.append(int(disabled))
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if password_hash is not None:
            updates.append("password_hash = ?")
            params.append(password_hash)
        if must_change_password is not None:
            updates.append("must_change_password = ?")
            params.append(int(must_change_password))
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.extend((now, user_id))
        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                tuple(params),
            )
            if cursor.rowcount == 0:
                return False
            if display_name is not None:
                conn.execute(
                    "UPDATE callers SET name = ?, updated_at = ? WHERE user_id = ?",
                    (display_name, now, user_id),
                )
            if disabled is not None:
                conn.execute(
                    "UPDATE callers SET disabled = ?, updated_at = ? WHERE user_id = ?",
                    (int(disabled), now, user_id),
                )
            return True

    def list_quota_ledger(
        self,
        caller_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """按 caller 读取预充值额度流水，最新记录在前。"""
        return self.fetch_all(
            """
            SELECT ledger_id, caller_id, task_id, delta, reason, balance_after, created_at
            FROM quota_ledger
            WHERE caller_id = ?
            ORDER BY rowid DESC
            LIMIT ? OFFSET ?
            """,
            (caller_id, limit, offset),
        )
    
    def get_caller(self, caller_id: str) -> Optional[Dict[str, Any]]:
        """Get caller by ID.
        
        Args:
            caller_id: Caller UUID.
            
        Returns:
            Caller data dict or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT caller_id, name, api_key_prefix, api_key_suffix,
                       default_postprocess_rule_id, expires_at, disabled,
                       last_used_at, created_at, updated_at, user_id
                FROM callers WHERE caller_id = ?
                """,
                (caller_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_caller_api_key(self, caller_id: str) -> Optional[str]:
        """Decrypt the current caller API key for explicit admin reveal."""
        from mineru_mcp.config import require_caller_key_master_key
        from mineru_mcp.caller_key_crypto import decrypt_api_key

        with self._conn() as conn:
            row = conn.execute(
                "SELECT api_key_encrypted FROM callers WHERE caller_id = ?",
                (caller_id,),
            ).fetchone()

        if not row:
            return None
        return decrypt_api_key(row["api_key_encrypted"], require_caller_key_master_key())
    
    def get_caller_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get caller by API key.
        
        Args:
            api_key: The API key (plaintext request token).
            
        Returns:
            Caller data dict or None if not found.
        """
        from mineru_mcp.config import require_caller_key_master_key
        from mineru_mcp.caller_key_crypto import get_api_key_digest

        digest = get_api_key_digest(api_key, require_caller_key_master_key())
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT caller_id, name, api_key_prefix, api_key_suffix,
                       default_postprocess_rule_id, expires_at, disabled,
                       last_used_at, created_at, updated_at, user_id
                FROM callers c
                WHERE api_key_hash = ? AND disabled = 0
                  AND (
                    user_id IS NULL
                    OR EXISTS (
                        SELECT 1 FROM users u
                        WHERE u.user_id = c.user_id AND u.disabled = 0
                    )
                  )
                """,
                (digest,)
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
            fields = """
                caller_id, name, api_key_prefix, api_key_suffix,
                default_postprocess_rule_id, expires_at, disabled,
                last_used_at, created_at, updated_at
            """
            if include_disabled:
                rows = conn.execute(f"SELECT {fields} FROM callers ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute(f"SELECT {fields} FROM callers WHERE disabled = 0 ORDER BY created_at DESC").fetchall()
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
            api_key: New API key (plaintext, encrypted before storage).
            api_key_prefix: New prefix for display.
            api_key_suffix: New suffix for display.
            expires_at: Optional new expiration timestamp. If not provided, keeps the existing expiration.
            
        Returns:
            True if reset, False if not found.
        """
        from mineru_mcp.config import require_caller_key_master_key
        from mineru_mcp.caller_key_crypto import encrypt_api_key

        encrypted = encrypt_api_key(api_key, require_caller_key_master_key())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            # If expires_at is not provided, keep the existing one
            if expires_at is None:
                cursor = conn.execute("""
                    UPDATE callers 
                    SET api_key_encrypted = ?, api_key_hash = ?, api_key_key_id = ?,
                        api_key_prefix = ?, api_key_suffix = ?,
                        updated_at = ?
                    WHERE caller_id = ?
                """, (
                    encrypted.ciphertext, encrypted.digest, encrypted.key_id,
                    encrypted.prefix, encrypted.suffix, now, caller_id,
                ))
            else:
                cursor = conn.execute("""
                    UPDATE callers 
                    SET api_key_encrypted = ?, api_key_hash = ?, api_key_key_id = ?,
                        api_key_prefix = ?, api_key_suffix = ?,
                        expires_at = ?, updated_at = ?
                    WHERE caller_id = ?
                """, (
                    encrypted.ciphertext, encrypted.digest, encrypted.key_id,
                    encrypted.prefix, encrypted.suffix, expires_at, now, caller_id,
                ))
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

    def update_admin_locale(self, username: str, locale: str) -> bool:
        """Update admin locale preference.

        Args:
            username: Admin username.
            locale: Locale string (e.g. 'zh-CN', 'en').

        Returns:
            True if updated, False if not found.
        """
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE admin_credentials
                SET locale = ?, updated_at = ?
                WHERE username = ?
            """, (locale, now, username))
            return cursor.rowcount > 0
