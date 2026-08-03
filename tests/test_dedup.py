"""队列内重复文件去重（事项 3）测试。

覆盖：
- 去重键计算：同内容同参数同键、不同参数不同键、file_hash NULL 无去重能力。
- 产物复制改名：源输出 → 目标输出逐文件按目标 pdf_name 改名，目标满足输出契约。
- 调度三分支：同键 completed 复用 / 同键 processing 等待 / 无同键正常领取。
- 并发防护：同一批内两个同键 pending 任务只领取一个。
- 失败回退：同键源任务 failed 时重复任务真实解析。
- 不同 backend 不复用。
"""

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import pytest

from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.config import MCPConfig, reset_config
from mineru_mcp.task_queue import FileManager, TaskDatabase
from mineru_mcp.task_queue.scheduler import TaskScheduler
from mineru_mcp.services.task_service import TaskService


def _minimal_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n%%EOF"
    )


def _principal(user_id: str = "user-dedup") -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id=user_id,
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name=user_id,
        caller_id=user_id,
    )


def _make_config(tmp_path):
    return MCPConfig(
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
        max_concurrent=2,
        task_timeout=3600,
        retry_limit=3,
        cleanup_days=30,
        db_path=str(tmp_path / "tasks.db"),
        output_root=str(tmp_path / "output"),
    )


@pytest.fixture
def service(tmp_path):
    config = _make_config(tmp_path)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    return TaskService(db=db, file_manager=fm, config=config)


class _RecordingProcessor:
    """Stub processor：记录被调度领取并拉起解析的任务 ID。"""

    def __init__(self):
        self.processed: list[str] = []
        self.active_tasks: dict[str, asyncio.Task] = {}

    def get_active_count(self):
        return 0

    def process_task(self, task_id, task_data):
        self.processed.append(task_id)
        return asyncio.sleep(0)

    def queue_auto_postprocess(self, task_id, task_data):
        pass


def _make_scheduler(db, output_root, processor=None, max_concurrent=2):
    scheduler = TaskScheduler(
        processor=processor or _RecordingProcessor(),
        db=db,
        max_concurrent=max_concurrent,
        poll_interval=3600,  # 不自动轮询，手动驱动
        timeout_check_enabled=False,
    )
    return scheduler


def _create_task_with_content(db, service, content, file_name, **params):
    """经 TaskService 建任务（落库 file_hash），返回 task_id。"""
    result = service.create_task_from_base64(
        file_base64=base64.b64encode(content).decode(),
        file_name=file_name,
        principal=_principal(),
        **params,
    )
    return result["task_id"]


def _write_source_artifacts(db, task_id, task_data, output_root):
    """为指定任务模拟解析产物（md + middle_json + content_list + images），返回 stored_name。"""
    task_dir = Path(task_data["task_dir"])
    stored = f"{task_id[:8]}.pdf"
    fm = FileManager(output_root=str(output_root))
    outputs = fm.get_output_files(task_dir, stored, task_data["backend"])
    outputs["output_dir"].mkdir(parents=True, exist_ok=True)
    outputs["md"].write_text(f"# {task_id}\ncontent\n", encoding="utf-8")
    outputs["middle_json"].write_text(json.dumps({"task": task_id}), encoding="utf-8")
    outputs["content_list"].write_text(json.dumps([{"task": task_id}]), encoding="utf-8")
    images = outputs["images_dir"]
    images.mkdir(parents=True, exist_ok=True)
    (images / "img1.png").write_bytes(b"PNGDATA")
    return stored


# ========== 去重键计算 ==========

def test_dedup_key_same_params_same_key(service):
    content = _minimal_pdf_bytes()
    t1 = _create_task_with_content(service.db, service, content, "a.pdf", lang="ch")
    t2 = _create_task_with_content(service.db, service, content, "b.pdf", lang="ch")

    k1 = service.db.dedup_key_for_task(service.db.get_task(t1))
    k2 = service.db.dedup_key_for_task(service.db.get_task(t2))
    assert k1 == k2


def test_dedup_key_diff_params_diff_key(service):
    content = _minimal_pdf_bytes()
    t1 = _create_task_with_content(service.db, service, content, "a.pdf", lang="ch")
    t2 = _create_task_with_content(service.db, service, content, "b.pdf", lang="en")

    k1 = service.db.dedup_key_for_task(service.db.get_task(t1))
    k2 = service.db.dedup_key_for_task(service.db.get_task(t2))
    assert k1 != k2


def test_dedup_key_null_hash_returns_none(service):
    """历史任务 file_hash 为 NULL → 无去重能力，key 为 None。"""
    db = service.db
    db.create_task(
        task_id="legacy-no-hash",
        task_dir="output/legacy",
        input_filename="legacy.pdf",
        backend="pipeline",
        owner_id="user",
    )
    assert db.dedup_key_for_task(db.get_task("legacy-no-hash")) is None


# ========== 产物复制改名 ==========

def test_copy_outputs_for_dedup_renames_and_completes(tmp_path):
    fm = FileManager(output_root=str(tmp_path / "output"))
    src_dir = tmp_path / "output" / "src"
    dst_dir = tmp_path / "output" / "dst"
    src_dir.mkdir(parents=True)
    dst_dir.mkdir(parents=True)

    # 源任务：task_id=aaaaaaaa，产物命名基于 aaaaaaaa.pdf
    src_stored = "aaaaaaaa.pdf"
    dst_stored = "bbbbbbbb.pdf"
    src_outputs = fm.get_output_files(src_dir, src_stored, "pipeline")
    src_outputs["output_dir"].mkdir(parents=True)
    src_outputs["md"].write_text("# src content", encoding="utf-8")
    src_outputs["middle_json"].write_text("{}", encoding="utf-8")
    src_outputs["content_list"].write_text("[]", encoding="utf-8")
    src_outputs["images_dir"].mkdir(parents=True)
    (src_outputs["images_dir"] / "pic.png").write_bytes(b"PNG")

    ok = fm.copy_outputs_for_dedup(
        source_task_dir=src_dir,
        source_input_filename=src_stored,
        source_backend="pipeline",
        target_task_dir=dst_dir,
        target_input_filename=dst_stored,
        target_backend="pipeline",
    )

    assert ok is True
    dst_outputs = fm.get_output_files(dst_dir, dst_stored, "pipeline")
    # 文件按目标 pdf_name 改名
    assert dst_outputs["md"].exists() and dst_outputs["md"].name == "bbbbbbbb.md"
    assert dst_outputs["middle_json"].exists() and dst_outputs["middle_json"].name == "bbbbbbbb_middle.json"
    assert dst_outputs["content_list"].exists()
    assert (dst_outputs["images_dir"] / "pic.png").exists()
    # 源文件不改名、不被移动
    assert src_outputs["md"].exists()
    # 内容一致
    assert dst_outputs["md"].read_text(encoding="utf-8") == "# src content"


def test_copy_outputs_for_dedup_source_missing_returns_false(tmp_path):
    fm = FileManager(output_root=str(tmp_path / "output"))
    src_dir = tmp_path / "output" / "src"
    dst_dir = tmp_path / "output" / "dst"
    src_dir.mkdir(parents=True)
    dst_dir.mkdir(parents=True)

    ok = fm.copy_outputs_for_dedup(
        source_task_dir=src_dir,
        source_input_filename="aaaaaaaa.pdf",
        source_backend="pipeline",
        target_task_dir=dst_dir,
        target_input_filename="bbbbbbbb.pdf",
        target_backend="pipeline",
    )
    assert ok is False


# ========== 调度去重三分支 ==========

def test_scheduler_reuses_completed_source(service, tmp_path):
    """分支 1：同键 completed 源 → 复制产物、标记 completed + dedup_source_task_id，不拉起 worker。"""
    content = _minimal_pdf_bytes()

    # 任务 1：真实解析并模拟完成
    t1 = _create_task_with_content(service.db, service, content, "one.pdf", lang="ch")
    service.db.update_status(t1, "processing", progress=0, message="Starting")
    task1 = service.db.get_task(t1)
    _write_source_artifacts(service.db, t1, task1, tmp_path / "output")
    service.db.update_status(t1, "completed", progress=100, message="Done")

    # 任务 2：同键 pending
    t2 = _create_task_with_content(service.db, service, content, "two.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    # t2 复用产物，不拉起 worker
    assert t2 not in proc.processed
    task2 = service.db.get_task(t2)
    assert task2["status"] == "completed"
    assert task2["dedup_source_task_id"] == t1
    # 产物已复制到 t2 目录
    fm = FileManager(output_root=str(tmp_path / "output"))
    t2_stored = f"{t2[:8]}.pdf"
    outputs = fm.get_output_files(Path(task2["task_dir"]), t2_stored, "pipeline")
    assert outputs["md"].exists()
    assert outputs["md"].read_text(encoding="utf-8") == f"# {t1}\ncontent\n"


def test_scheduler_waits_when_peer_processing(service, tmp_path):
    """分支 2：同键 processing 源 → 本任务保持 pending，不领取。"""
    content = _minimal_pdf_bytes()

    t1 = _create_task_with_content(service.db, service, content, "one.pdf", lang="ch")
    service.db.update_status(t1, "processing", progress=0, message="Starting")

    t2 = _create_task_with_content(service.db, service, content, "two.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    # t1 已在 processing（模拟正在解析），不是本批领取的对象；t2 同键应等待
    assert t1 not in proc.processed
    assert t2 not in proc.processed
    assert service.db.get_task(t1)["status"] == "processing"
    assert service.db.get_task(t2)["status"] == "pending"


def test_scheduler_claims_when_no_peer(service, tmp_path):
    """无同键任务 → 正常领取解析。"""
    content = _minimal_pdf_bytes()
    t1 = _create_task_with_content(service.db, service, content, "solo.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    assert t1 in proc.processed
    assert service.db.get_task(t1)["status"] == "processing"


def test_scheduler_failed_source_falls_back_to_real_parse(service, tmp_path):
    """失败回退：同键源 failed → 重复任务真实解析。"""
    content = _minimal_pdf_bytes()

    t1 = _create_task_with_content(service.db, service, content, "one.pdf", lang="ch")
    service.db.update_status(t1, "processing", progress=0, message="Starting")
    service.db.update_status(t1, "failed", error="boom", progress=-1)

    t2 = _create_task_with_content(service.db, service, content, "two.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    assert t2 in proc.processed
    assert service.db.get_task(t2)["status"] == "processing"


def test_scheduler_same_batch_concurrent_guard(service, tmp_path):
    """并发防护：同一批内两个同键 pending 任务只领取一个。"""
    content = _minimal_pdf_bytes()

    t1 = _create_task_with_content(service.db, service, content, "one.pdf", lang="ch")
    t2 = _create_task_with_content(service.db, service, content, "two.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc, max_concurrent=2)
    asyncio.run(scheduler._fetch_pending_tasks())

    processed = [t for t in proc.processed]
    assert len(processed) == 1
    # 另一个保持 pending
    remaining = [t for t in (t1, t2) if t not in processed]
    assert len(remaining) == 1
    assert service.db.get_task(remaining[0])["status"] == "pending"


def test_scheduler_diff_backend_no_dedup(service, tmp_path):
    """不同 backend → 去重键不同，不复用。"""
    content = _minimal_pdf_bytes()

    # 任务 1 用 pipeline 并完成
    t1 = _create_task_with_content(service.db, service, content, "one.pdf", backend="pipeline")
    service.db.update_status(t1, "processing", progress=0, message="Starting")
    task1 = service.db.get_task(t1)
    _write_source_artifacts(service.db, t1, task1, tmp_path / "output")
    service.db.update_status(t1, "completed", progress=100, message="Done")

    # 任务 2 用 vlm-http-client（不同 backend + server_url）
    t2 = _create_task_with_content(
        service.db, service, content, "two.pdf",
        backend="vlm-http-client", server_url="http://localhost:30000/v1",
    )

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    assert t2 in proc.processed
    assert service.db.get_task(t2)["status"] == "processing"


def test_scheduler_completed_source_missing_artifacts_falls_back(service, tmp_path):
    """源任务 completed 但产物已被清理（目录缺失）→ 退化为真实解析。"""
    content = _minimal_pdf_bytes()

    # 任务 1：completed 但无产物（模拟 cleanup 删目录）
    t1 = _create_task_with_content(service.db, service, content, "one.pdf", lang="ch")
    service.db.update_status(t1, "processing", progress=0, message="Starting")
    service.db.update_status(t1, "completed", progress=100, message="Done")

    # 任务 2：同键 pending
    t2 = _create_task_with_content(service.db, service, content, "two.pdf", lang="ch")

    proc = _RecordingProcessor()
    scheduler = _make_scheduler(service.db, tmp_path / "output", processor=proc)
    asyncio.run(scheduler._fetch_pending_tasks())

    # 源产物缺失 → 复制失败 → t2 真实解析
    assert t2 in proc.processed
    assert service.db.get_task(t2)["status"] == "processing"
