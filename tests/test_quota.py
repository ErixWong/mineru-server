import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mineru_mcp.api import create_api_app
from mineru_mcp.config import get_config, reset_config
from mineru_mcp.errors import ErrorCode, MCPError
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import reset_task_service
from mineru_mcp.services.quota_service import QuotaService
from mineru_mcp.task_queue import FileManager, TaskDatabase, TaskStateService
from mineru_mcp.task_queue.file_manager import stored_filename


def _setup_db(tmp_path, monkeypatch):
    output_root = tmp_path / "output"
    db_path = output_root / "tasks.db"
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("MINERU_DB_PATH", str(db_path))
    reset_config()
    reset_task_service()
    return TaskDatabase(db_path=str(db_path))


def _create_caller(db, caller_id="caller-a"):
    db.create_caller(
        caller_id=caller_id,
        name="Quota caller",
        api_key=f"token-{caller_id}",
        api_key_prefix="toke",
        api_key_suffix="ller",
    )


def _create_task(db, tmp_path, task_id, caller_id, pages_reserved):
    db.create_task(
        task_id=task_id,
        task_dir=str(tmp_path / task_id),
        input_filename=f"{task_id}.pdf",
        backend="pipeline",
        owner_id=caller_id,
        owner_type="api_key",
        caller_id=caller_id,
        pages_reserved=pages_reserved,
    )


def test_migration_v17_preserves_existing_caller_and_task(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db, "legacy-caller")
    db.create_task(
        task_id="legacy-task",
        task_dir=str(tmp_path / "legacy-task"),
        input_filename="legacy.pdf",
        backend="pipeline",
        owner_id="legacy-caller",
        owner_type="api_key",
        caller_id="legacy-caller",
    )

    with sqlite3.connect(db.db_path) as conn:
        conn.execute("ALTER TABLE callers DROP COLUMN quota_total_pages")
        conn.execute("ALTER TABLE tasks DROP COLUMN pages_reserved")
        conn.execute("ALTER TABLE tasks DROP COLUMN pages_billed")
        conn.execute("ALTER TABLE tasks DROP COLUMN quota_released")
        conn.execute("DROP TABLE quota_ledger")
        conn.execute("PRAGMA user_version = 16")

    upgraded = TaskDatabase(db_path=str(db.db_path))
    task = upgraded.get_task("legacy-task")
    caller = upgraded.fetch_one(
        "SELECT caller_id, quota_total_pages FROM callers WHERE caller_id = ?",
        ("legacy-caller",),
    )
    assert upgraded.SCHEMA_VERSION == 20
    assert task["status"] == "pending"
    assert task["input_filename"] == "legacy.pdf"
    assert task["pages_reserved"] is None
    assert task["pages_billed"] is None
    assert task["quota_released"] == 0
    assert caller == {"caller_id": "legacy-caller", "quota_total_pages": None}
    assert upgraded.count(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'quota_ledger'"
    ) == 1


def test_estimate_pages_clips_image_to_selected_range(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"png")

    assert QuotaService.estimate_pages(image, 0, 0) == 1
    assert QuotaService.estimate_pages(image, 1, 99999) == 0
    assert QuotaService.estimate_pages(image, 0, 99999) == 1


def test_reserve_sufficient_insufficient_unlimited_and_no_caller(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 10 WHERE caller_id = ?", ("caller-a",))
    quota = QuotaService(db)

    assert quota.reserve("caller-a", "task-one", 4) == 6
    assert db.get_quota_balance("caller-a") == 6
    with pytest.raises(MCPError) as exc_info:
        quota.reserve("caller-a", "task-two", 7)
    assert exc_info.value.code == ErrorCode.QUOTA_EXCEEDED
    assert exc_info.value.http_status == 403
    assert exc_info.value.details["reason"] == "剩余 6 页 / 本次需 7 页"

    db.execute("UPDATE callers SET quota_total_pages = NULL WHERE caller_id = ?", ("caller-a",))
    assert quota.reserve("caller-a", "task-unlimited", 100) is None
    assert quota.reserve(None, "task-single-user", 100) is None
    assert db.count("SELECT COUNT(*) FROM quota_ledger") == 1


def test_settle_refunds_or_charges_difference_and_release_is_idempotent(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 10 WHERE caller_id = ?", ("caller-a",))
    quota = QuotaService(db)

    _create_task(db, tmp_path, "task-refund", "caller-a", 5)
    quota.reserve("caller-a", "task-refund", 5)
    assert quota.settle("caller-a", "task-refund", 3) == 3
    assert db.get_task("task-refund")["pages_billed"] == 3
    assert db.get_quota_balance("caller-a") == 7

    _create_task(db, tmp_path, "task-charge", "caller-a", 2)
    quota.reserve("caller-a", "task-charge", 2)
    assert quota.settle("caller-a", "task-charge", 4) == 4
    assert db.get_task("task-charge")["pages_billed"] == 4
    assert db.get_quota_balance("caller-a") == 3

    _create_task(db, tmp_path, "task-release", "caller-a", 3)
    quota.reserve("caller-a", "task-release", 3)
    assert db.get_quota_balance("caller-a") == 0
    assert quota.release("caller-a", "task-release") is True
    assert quota.release("caller-a", "task-release") is False
    assert db.get_task("task-release")["quota_released"] == 1
    assert db.get_quota_balance("caller-a") == 3
    assert db.count(
        "SELECT COUNT(*) FROM quota_ledger WHERE task_id = ? AND reason = 'task_release'",
        ("task-release",),
    ) == 1


def test_complete_settles_from_middle_json_pdf_info(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 10 WHERE caller_id = ?", ("caller-a",))
    task_dir = tmp_path / "task-actual"
    db.create_task(
        task_id="task-actual",
        task_dir=str(task_dir),
        input_filename="task-actual.pdf",
        backend="pipeline",
        owner_id="caller-a",
        owner_type="api_key",
        caller_id="caller-a",
        pages_reserved=3,
    )
    quota = QuotaService(db)
    quota.reserve("caller-a", "task-actual", 3)
    db.update_status("task-actual", "processing")

    stored_name = stored_filename("task-actual", "task-actual.pdf")
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / stored_name).write_bytes(b"%PDF-1.4")
    output_files = FileManager(output_root=str(tmp_path)).get_output_files(
        task_dir,
        stored_name,
        "pipeline",
    )
    output_files["middle_json"].parent.mkdir(parents=True)
    output_files["middle_json"].write_text('{"pdf_info": [{}, {}]}', encoding="utf-8")

    assert TaskStateService(db).complete("task-actual") is True
    assert db.get_task("task-actual")["pages_billed"] == 2
    assert db.get_quota_balance("caller-a") == 8


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled"])
def test_terminal_state_transitions_release_reserved_pages(tmp_path, monkeypatch, terminal_status):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 8 WHERE caller_id = ?", ("caller-a",))
    _create_task(db, tmp_path, f"task-{terminal_status}", "caller-a", 3)
    quota = QuotaService(db)
    quota.reserve("caller-a", f"task-{terminal_status}", 3)
    db.update_status(f"task-{terminal_status}", "processing")

    state = TaskStateService(db)
    if terminal_status == "failed":
        transitioned = state.fail(f"task-{terminal_status}", "parse failed")
    else:
        transitioned = state.cancel(f"task-{terminal_status}")

    assert transitioned is True
    assert db.get_task(f"task-{terminal_status}")["quota_released"] == 1
    assert db.get_quota_balance("caller-a") == 8


def test_top_up_adds_quota_and_appends_income_ledger(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 5 WHERE caller_id = ?", ("caller-a",))

    entry = QuotaService(db).top_up("caller-a", 12, "管理员补充")

    assert entry["delta"] == 12
    assert entry["balance_after"] == 17
    assert db.get_quota_balance("caller-a") == 17
    caller = db.fetch_one(
        "SELECT quota_total_pages FROM callers WHERE caller_id = ?",
        ("caller-a",),
    )
    assert caller["quota_total_pages"] == 17

    _create_caller(db, "caller-b")
    unlimited_entry = QuotaService(db).top_up("caller-b", 4, "启用预充值")
    assert unlimited_entry["balance_after"] == 4
    assert db.get_quota_balance("caller-b") == 4


def test_concurrent_reservations_do_not_oversell(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 5 WHERE caller_id = ?", ("caller-a",))
    quota = QuotaService(db)

    def reserve(index):
        try:
            quota.reserve("caller-a", f"parallel-task-{index}", 1)
            return True
        except MCPError as exc:
            assert exc.code == ErrorCode.QUOTA_EXCEEDED
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        outcomes = list(executor.map(reserve, range(10)))

    assert sum(outcomes) == 5
    assert db.get_quota_balance("caller-a") == 0
    assert db.count("SELECT COUNT(*) FROM quota_ledger WHERE delta = -1") == 5


def test_submit_rejects_insufficient_quota_with_http_403_and_reserves_when_allowed(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    _create_caller(db)
    db.execute("UPDATE callers SET quota_total_pages = 0 WHERE caller_id = ?", ("caller-a",))
    principal = CurrentPrincipal(
        principal_id="caller-a",
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name="Quota caller",
        caller_id="caller-a",
    )
    client = TestClient(create_api_app())
    upload = b"%PDF-1.4\nquota test input"

    with patch("mineru_mcp.api.get_principal_from_request", return_value=principal):
        rejected = client.post(
            "/tasks",
            data={"backend": "pipeline"},
            files={"file": ("sample.pdf", upload, "application/pdf")},
        )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["error"] == "QUOTA_EXCEEDED"
    assert rejected.json()["detail"]["detail"]["reason"] == "剩余 0 页 / 本次需 1 页"
    assert db.count("SELECT COUNT(*) FROM tasks") == 0

    db.execute("UPDATE callers SET quota_total_pages = 2 WHERE caller_id = ?", ("caller-a",))
    with patch("mineru_mcp.api.get_principal_from_request", return_value=principal):
        accepted = client.post(
            "/tasks",
            data={"backend": "pipeline"},
            files={"file": ("sample.pdf", upload, "application/pdf")},
        )
    assert accepted.status_code == 200
    task = db.get_task(accepted.json()["task_id"])
    assert task["pages_reserved"] == 1
    assert db.get_quota_balance("caller-a") == 1
