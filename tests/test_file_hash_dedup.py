"""文件内容 hash 落库与去重基础测试。

覆盖事项 2：提交文件时流式计算 sha256 并落库（base64 与 file 两条路径），
以及 v15 迁移幂等性。去重逻辑本身（事项 3）在下一轮实现，这里只验证
hash 数据基础正确、可作为后续去重键。
"""

import base64
import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.config import MCPConfig, reset_config
from mineru_mcp.task_queue import FileManager, TaskDatabase
from mineru_mcp.services.task_service import TaskService


def _minimal_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n%%EOF"
    )


def _principal(user_id: str = "user-hash") -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id=user_id,
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name=user_id,
        caller_id=user_id,
    )


@pytest.fixture
def service(tmp_path):
    db_path = tmp_path / "tasks.db"
    output_root = tmp_path / "output"
    db = TaskDatabase(db_path=str(db_path))
    fm = FileManager(output_root=str(output_root))
    config = MCPConfig(
        default_backend="pipeline",
        vlm_base_url=None,
        vlm_api_key=None,
        vlm_model=None,
        vlm_max_concurrency=2,
        title_api_key=None,
        title_base_url=None,
        title_model=None,
        postprocess_context_size=131072,
        postprocess_max_concurrent=2,
        server_name="test",
        server_mode="http",
        http_host="127.0.0.1",
        http_port=8002,
        log_level="INFO",
        max_concurrent=1,
        task_timeout=3600,
        retry_limit=3,
        cleanup_days=30,
        db_path=str(db_path),
        output_root=str(output_root),
    )
    return TaskService(db=db, file_manager=fm, config=config)


def test_base64_task_records_file_hash_and_size(service):
    """base64 路径：file_hash 为内容 sha256，file_size 为字节数。"""
    content = _minimal_pdf_bytes()
    expected_hash = hashlib.sha256(content).hexdigest()

    result = service.create_task_from_base64(
        file_base64=base64.b64encode(content).decode(),
        file_name="doc.pdf",
        principal=_principal(),
    )
    task = service.db.get_task(result["task_id"])

    assert task["file_hash"] == expected_hash
    assert task["file_size"] == len(content)


def test_file_stream_task_records_file_hash_and_size(service, tmp_path):
    """file 路径：流式拷贝同时散列，hash 与源文件一致。"""
    content = _minimal_pdf_bytes() + b"\n%extra"
    source = tmp_path / "source.pdf"
    source.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()

    result = service.create_task_from_file(
        source_path=source,
        file_name="stream.pdf",
        principal=_principal(),
    )
    task = service.db.get_task(result["task_id"])

    assert task["file_hash"] == expected_hash
    assert task["file_size"] == len(content)


def test_same_content_same_hash_across_paths(service, tmp_path):
    """同一内容经 base64 与 file 两条路径应得到相同 hash（去重键基础）。"""
    content = _minimal_pdf_bytes()

    r1 = service.create_task_from_base64(
        file_base64=base64.b64encode(content).decode(),
        file_name="a.pdf",
        principal=_principal("user-a"),
    )
    source = tmp_path / "b.pdf"
    source.write_bytes(content)
    r2 = service.create_task_from_file(
        source_path=source,
        file_name="b.pdf",
        principal=_principal("user-b"),
    )

    t1 = service.db.get_task(r1["task_id"])
    t2 = service.db.get_task(r2["task_id"])
    assert t1["file_hash"] == t2["file_hash"]
    assert t1["file_hash"] == hashlib.sha256(content).hexdigest()


def test_different_content_different_hash(service):
    """不同内容 hash 不同（预筛唯一性）。"""
    r1 = service.create_task_from_base64(
        file_base64=base64.b64encode(_minimal_pdf_bytes()).decode(),
        file_name="one.pdf",
        principal=_principal(),
    )
    r2 = service.create_task_from_base64(
        file_base64=base64.b64encode(_minimal_pdf_bytes() + b"x").decode(),
        file_name="two.pdf",
        principal=_principal(),
    )

    t1 = service.db.get_task(r1["task_id"])
    t2 = service.db.get_task(r2["task_id"])
    assert t1["file_hash"] != t2["file_hash"]


def test_migration_v15_adds_hash_columns_and_index(tmp_path):
    """v15 迁移：旧库升级后具备 file_hash/file_size 列与索引。"""
    db_path = tmp_path / "migrate.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 构造一个停留在 v14 的旧库（建表结构含 v14 之前的列，缺 file_hash/file_size）
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 14")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                task_dir TEXT NOT NULL,
                input_filename TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                owner_type TEXT NOT NULL DEFAULT 'single_user',
                backend TEXT DEFAULT 'vlm-auto-engine',
                parse_method TEXT DEFAULT 'auto',
                lang TEXT DEFAULT 'ch',
                formula_enable INTEGER DEFAULT 1,
                table_enable INTEGER DEFAULT 1,
                image_analysis INTEGER DEFAULT 1,
                server_url TEXT,
                return_md INTEGER DEFAULT 1,
                return_middle_json INTEGER DEFAULT 0,
                return_model_output INTEGER DEFAULT 0,
                return_content_list INTEGER DEFAULT 0,
                return_images INTEGER DEFAULT 0,
                start_page_id INTEGER DEFAULT 0,
                end_page_id INTEGER DEFAULT 99999,
                progress INTEGER DEFAULT 0,
                message TEXT DEFAULT 'Task created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                timeout_seconds INTEGER DEFAULT 3600,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                enable_postprocess INTEGER DEFAULT 0,
                postprocess_rule_id TEXT,
                postprocess_context_size INTEGER,
                postprocess_status TEXT DEFAULT 'not_enabled',
                postprocess_output_filename TEXT,
                postprocess_rule_title_snapshot TEXT,
                postprocess_prompt_snapshot TEXT,
                caller_id TEXT,
                request_summary TEXT,
                result_summary TEXT
            );
            """
        )

    db = TaskDatabase(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(tasks)").fetchall()
        }

    assert user_version == TaskDatabase.SCHEMA_VERSION
    assert {"file_hash", "file_size"}.issubset(cols)
    assert "idx_tasks_file_hash" in indexes


def test_migration_idempotent_on_reinit(tmp_path):
    """迁移幂等：同一 db 重复初始化不抛错。"""
    db_path = tmp_path / "idem.db"
    db1 = TaskDatabase(db_path=str(db_path))
    db2 = TaskDatabase(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == TaskDatabase.SCHEMA_VERSION
    assert db1.db_path == db2.db_path


def test_migration_v16_adds_dedup_source_column(tmp_path):
    """v16 迁移：v15 库升级后具备 dedup_source_task_id 列。"""
    db_path = tmp_path / "migrate16.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 构造停留在 v15 的库（tasks 表含 v15 全部列，缺 dedup_source_task_id）
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 15")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                task_dir TEXT NOT NULL,
                input_filename TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                owner_type TEXT NOT NULL DEFAULT 'single_user',
                backend TEXT DEFAULT 'vlm-auto-engine',
                lang TEXT DEFAULT 'ch',
                file_hash TEXT,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            """
        )

    db = TaskDatabase(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

    assert user_version == TaskDatabase.SCHEMA_VERSION
    assert "dedup_source_task_id" in cols


def test_legacy_task_hash_is_null_without_backfill(service):
    """历史任务 file_hash 为 NULL 属正常状态，不回填。"""
    # 模拟历史数据：直接写一条无 hash 的任务
    task_id = "legacy-task-0001"
    task_dir = str(service.file_manager.output_root / "legacy")
    service.db.create_task(
        task_id=task_id,
        task_dir=task_dir,
        input_filename="legacy.pdf",
        backend="pipeline",
        owner_id="user-hash",
        owner_type=PrincipalType.API_KEY.value,
    )

    task = service.db.get_task(task_id)
    assert task["file_hash"] is None
    assert task["file_size"] is None


def test_hash_matches_on_disk_content(service, tmp_path):
    """核心不变量：落库 file_hash 必须等于任务目录中实际落盘文件内容的 sha256。

    防止"hash 记了但文件写偏"的静默不一致（去重键失效的直接根因）。
    """
    content = _minimal_pdf_bytes() + b"\n%consistency-check"
    source = tmp_path / "on-disk.pdf"
    source.write_bytes(content)

    result = service.create_task_from_file(
        source_path=source,
        file_name="on-disk.pdf",
        principal=_principal(),
    )
    task = service.db.get_task(result["task_id"])
    task_dir = Path(task["task_dir"])

    # 任务目录里应恰好有一个输入文件；读回它算 hash 与落库值比对
    on_disk_files = [p for p in task_dir.rglob("*.pdf") if p.is_file()]
    assert len(on_disk_files) == 1
    on_disk_hash = hashlib.sha256(on_disk_files[0].read_bytes()).hexdigest()

    assert task["file_hash"] == on_disk_hash
    assert task["file_size"] == len(content)


def test_base64_hash_matches_on_disk_content(service):
    """base64 路径同样满足落盘内容 == 落库 hash。"""
    content = _minimal_pdf_bytes()

    result = service.create_task_from_base64(
        file_base64=base64.b64encode(content).decode(),
        file_name="b64-disk.pdf",
        principal=_principal(),
    )
    task = service.db.get_task(result["task_id"])
    task_dir = Path(task["task_dir"])

    on_disk_files = [p for p in task_dir.rglob("*.pdf") if p.is_file()]
    assert len(on_disk_files) == 1
    on_disk_hash = hashlib.sha256(on_disk_files[0].read_bytes()).hexdigest()
    assert task["file_hash"] == on_disk_hash


def test_hashing_path_rejects_uncovered_write_api(tmp_path):
    """fail-fast：未覆盖的写入 API 应直接报错，而非静默绕过散列导致 hash 与落盘内容不一致。"""
    from mineru_mcp.services.task_service import _HashingPath

    hashing = _HashingPath(tmp_path / "target.pdf")

    # write_text 未覆盖：应 AttributeError 而非静默写盘
    with pytest.raises(AttributeError):
        hashing.write_text("hello")

    # 文本写模式 open("w")：写入会绕过 hash，fail-fast
    with pytest.raises(AttributeError, match="文本写模式"):
        hashing.open("w")

    # 二进制写模式 open("wb")：正常拦截并计入 hash
    with hashing.open("wb") as f:
        f.write(b"abc")
    assert hashing.size == 3
    assert hashing.hexdigest == hashlib.sha256(b"abc").hexdigest()

    # 二进制读模式 open("rb")：读不计入 hash，透传
    with hashing.open("rb") as f:
        assert f.read() == b"abc"
    assert hashing.size == 3
