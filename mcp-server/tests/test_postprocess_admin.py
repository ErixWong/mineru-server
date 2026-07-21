"""Admin-level regression tests for postprocess plans/actions (M3) and downloads (H2)."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password
from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase


def _setup_admin_client(tmp_path, monkeypatch, *, configure_llm: bool = False):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
    if configure_llm:
        monkeypatch.setenv("MINERU_TITLE_API_KEY", "sk-dummy")
        monkeypatch.setenv("MINERU_TITLE_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("MINERU_TITLE_MODEL", "test-model")
    reset_config()
    init_default_admin()
    TaskDatabase(db_path=str(tmp_path / "tasks.db")).set_admin_password_change_required("admin", False)

    client = TestClient(create_api_app())
    login_response = client.post(
        "/admin/login",
        json={"username": "admin", "password": get_default_admin_password()},
        headers={"Origin": "http://testserver"},
    )
    assert login_response.status_code == 200
    csrf_token = login_response.cookies.get("admin_csrf")
    assert csrf_token
    write_headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf_token}
    return client, write_headers


def _create_action(client, headers, name="清洗动作") -> str:
    response = client.post(
        "/admin/postprocess-actions",
        json={"name": name, "prompt": "清洗文本", "output_filename": "final.md"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["action_id"]


def _create_plan(client, headers, title="测试方案") -> str:
    action_id = _create_action(client, headers)
    response = client.post(
        "/admin/postprocess-plans",
        json={"title": title, "steps": [{"action_id": action_id}]},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["plan_id"]


def _create_caller_with_default_plan(client, headers, plan_id: str) -> str:
    response = client.post(
        "/admin/callers",
        json={"name": "caller-a", "default_postprocess_rule_id": plan_id},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["caller_id"]


# ========== M3: caller reference guards on delete/disable ==========


def test_delete_plan_referenced_by_caller_returns_409(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)
    caller_id = _create_caller_with_default_plan(client, headers, plan_id)

    response = client.delete(f"/admin/postprocess-plans/{plan_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "PLAN_REFERENCED_BY_CALLERS"

    # Clearing the caller default releases the plan.
    clear = client.patch(
        f"/admin/callers/{caller_id}",
        json={"default_postprocess_rule_id": ""},
        headers=headers,
    )
    assert clear.status_code == 200

    response = client.delete(f"/admin/postprocess-plans/{plan_id}", headers=headers)
    assert response.status_code == 200


def test_disable_plan_referenced_by_caller_returns_409(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)
    _create_caller_with_default_plan(client, headers, plan_id)

    response = client.put(
        f"/admin/postprocess-plans/{plan_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "PLAN_REFERENCED_BY_CALLERS"

    # Updates that do not disable the plan remain allowed.
    response = client.put(
        f"/admin/postprocess-plans/{plan_id}",
        json={"title": "改名"},
        headers=headers,
    )
    assert response.status_code == 200


def test_delete_unreferenced_plan_succeeds(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)

    response = client.delete(f"/admin/postprocess-plans/{plan_id}", headers=headers)
    assert response.status_code == 200


# ========== actions CRUD 与引用保护 ==========


def test_action_crud_and_reference_guard(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    action_id = _create_action(client, headers)

    # 更新 prompt
    response = client.put(
        f"/admin/postprocess-actions/{action_id}",
        json={"prompt": "新提示词"},
        headers=headers,
    )
    assert response.status_code == 200

    # 被 plan 引用后：删除 409、停用 409
    plan_response = client.post(
        "/admin/postprocess-plans",
        json={"title": "P", "steps": [{"action_id": action_id}]},
        headers=headers,
    )
    assert plan_response.status_code == 200
    plan_id = plan_response.json()["plan_id"]

    response = client.delete(f"/admin/postprocess-actions/{action_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "ACTION_REFERENCED_BY_PLANS"

    response = client.put(
        f"/admin/postprocess-actions/{action_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "ACTION_REFERENCED_BY_PLANS"

    # 删除 plan 后 action 可删
    response = client.delete(f"/admin/postprocess-plans/{plan_id}", headers=headers)
    assert response.status_code == 200
    response = client.delete(f"/admin/postprocess-actions/{action_id}", headers=headers)
    assert response.status_code == 200


def test_plan_rejects_unknown_action(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    response = client.post(
        "/admin/postprocess-plans",
        json={"title": "P", "steps": [{"action_id": "ppa-missing"}]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_PLAN_STEPS"


def test_plan_rejects_empty_steps(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    response = client.post(
        "/admin/postprocess-plans",
        json={"title": "P", "steps": []},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_PLAN_STEPS"


def test_list_plans_returns_items_and_context_size(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)
    response = client.get("/admin/postprocess-plans")
    assert response.status_code == 200
    body = response.json()
    assert body["default_context_size"] > 0
    plan = next(item for item in body["items"] if item["plan_id"] == plan_id)
    assert plan["title"] == "测试方案"
    assert len(plan["steps"]) == 1


# ========== 手动触发 run（admin） ==========


def test_admin_trigger_and_cancel_postprocess_run(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch, configure_llm=True)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)

    # 触发 run
    response = client.post(
        f"/admin/tasks/{task_id}/postprocess-runs",
        json={"plan_id": plan_id},
        headers=headers,
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    # 列表可见（pending，步骤为 pending）
    response = client.get(f"/admin/tasks/{task_id}/postprocess-runs")
    assert response.status_code == 200
    runs = response.json()["items"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["status"] == "pending"
    assert runs[0]["trigger_source"] == "manual"
    assert runs[0]["steps"][0]["status"] == "pending"
    assert runs[0]["plan_title"] == "测试方案"

    # 取消 pending run
    response = client.post(f"/admin/postprocess-runs/{run_id}/cancel", headers=headers)
    assert response.status_code == 200
    response = client.get(f"/admin/tasks/{task_id}/postprocess-runs")
    assert response.json()["items"][0]["status"] == "cancelled"

    # 终态不可再取消
    response = client.post(f"/admin/postprocess-runs/{run_id}/cancel", headers=headers)
    assert response.status_code == 409


def test_admin_trigger_run_rejects_non_completed_task(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch, configure_llm=True)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("processing", task_id))
    plan_id = _create_plan(client, headers)

    response = client.post(
        f"/admin/tasks/{task_id}/postprocess-runs",
        json={"plan_id": plan_id},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "TASK_NOT_COMPLETED"


def test_admin_trigger_run_rejects_unknown_plan(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch, configure_llm=True)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)

    response = client.post(
        f"/admin/tasks/{task_id}/postprocess-runs",
        json={"plan_id": "ppp-missing"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_POSTPROCESS_PLAN"


def test_admin_trigger_run_rejects_unconfigured_llm(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)
    plan_id = _create_plan(client, headers)

    response = client.post(
        f"/admin/tasks/{task_id}/postprocess-runs",
        json={"plan_id": plan_id},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "POSTPROCESS_LLM_NOT_CONFIGURED"


# ========== H2: admin download of postprocessed artifact ==========


def _make_task_with_postprocess_artifact(tmp_path, monkeypatch):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id = uuid.uuid4().hex
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (task_dir / "input.pdf").write_bytes(b"%PDF-fake")
    (output_dir / "input.md").write_text("# 原文\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    (output_dir / "final.md").write_text("# 后处理结果\n", encoding="utf-8")
    db.create_task(
        task_id=task_id,
        task_dir=str(task_dir),
        input_filename="input.pdf",
        backend="pipeline",
        enable_postprocess=True,
        postprocess_rule_id="ppr-x",
        postprocess_output_filename="final.md",
        postprocess_status="completed",
    )
    db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("completed", task_id))
    return task_id


def test_admin_can_download_postprocessed_artifact(tmp_path, monkeypatch):
    client, _ = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)

    response = client.get(
        f"/admin/tasks/{task_id}/deliverables/download",
        params={"download_key": "input/auto/final.md"},
    )
    assert response.status_code == 200
    # write_text translates newlines to os.linesep on Windows; normalize for comparison
    assert response.text.replace("\r\n", "\n") == "# 后处理结果\n"


def test_admin_download_rejects_unknown_key(tmp_path, monkeypatch):
    client, _ = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)

    response = client.get(
        f"/admin/tasks/{task_id}/deliverables/download",
        params={"download_key": "input/auto/nonexistent.md"},
    )
    assert response.status_code == 404


# ========== round06 Item 1: admin download rejects non-completed tasks ==========


def _make_cancelled_task_with_orphan_file(tmp_path, monkeypatch):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id = uuid.uuid4().hex
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (task_dir / "input.pdf").write_bytes(b"%PDF-fake")
    (output_dir / "input.md").write_text("# 原文\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    (output_dir / "final.md").write_text("# 后处理结果\n", encoding="utf-8")
    db.create_task(
        task_id=task_id, task_dir=str(task_dir),
        input_filename="input.pdf", backend="pipeline",
        enable_postprocess=True,
        postprocess_rule_id="ppr-x",
        postprocess_output_filename="final.md",
        postprocess_status="failed",
    )
    # Overwrite status to cancelled to simulate the orphan-file scenario
    db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("cancelled", task_id))
    return task_id


def test_admin_download_rejects_cancelled_task_with_orphan_file(tmp_path, monkeypatch):
    """Item 1: non-completed task must not serve orphan postprocess files."""
    client, _ = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_cancelled_task_with_orphan_file(tmp_path, monkeypatch)

    response = client.get(
        f"/admin/tasks/{task_id}/deliverables/download",
        params={"download_key": "input/auto/final.md"},
    )
    assert response.status_code == 404


# ========== 创建任务指派归属调用方 ==========


def _create_caller(client, headers, name="caller-a") -> str:
    response = client.post("/admin/callers", json={"name": name}, headers=headers)
    assert response.status_code == 200
    return response.json()["caller_id"]


def _submit_admin_task(client, headers, **form_fields):
    data = {"lang": "ch", "backend": "pipeline", **form_fields}
    files = {"file": ("sample.pdf", b"%PDF-1.4\nmock pdf content", "application/pdf")}
    return client.post("/admin/tasks", data=data, files=files, headers=headers)


def test_admin_create_task_assigns_caller_ownership(tmp_path, monkeypatch):
    """指派 caller 后，任务归属该 caller，其 API key 主体可通过 owner 校验。"""
    from mineru_mcp.services import reset_task_service, get_task_service
    from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType

    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    reset_task_service()
    caller_id = _create_caller(client, headers)

    response = _submit_admin_task(client, headers, caller_id=caller_id)
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task = db.get_task(task_id)
    assert task["caller_id"] == caller_id
    assert task["owner_id"] == caller_id
    assert task["owner_type"] == "api_key"

    # 该 caller 的 key 主体通过 owner 校验；其他 caller 不通过
    service = get_task_service()
    owner_principal = CurrentPrincipal(
        principal_id=caller_id, principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="caller-a", caller_id=caller_id,
    )
    other_principal = CurrentPrincipal(
        principal_id="someone-else", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="x", caller_id="someone-else",
    )
    assert service._check_task_ownership(task_id, owner_principal) is True
    assert service._check_task_ownership(task_id, other_principal) is False


def test_admin_create_task_without_caller_keeps_admin_console_owner(tmp_path, monkeypatch):
    """不指派时维持现状：归属 admin-console，caller_id 为 NULL。"""
    from mineru_mcp.services import reset_task_service

    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    reset_task_service()

    response = _submit_admin_task(client, headers)
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task = db.get_task(task_id)
    assert task["caller_id"] is None
    assert task["owner_id"] == "admin-console"
    assert task["owner_type"] == "single_user"


def test_admin_create_task_rejects_unknown_caller(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    response = _submit_admin_task(client, headers, caller_id="missing-caller")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_CALLER"


def test_admin_create_task_rejects_disabled_caller(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    caller_id = _create_caller(client, headers)
    disable = client.patch(f"/admin/callers/{caller_id}", json={"disabled": True}, headers=headers)
    assert disable.status_code == 200

    response = _submit_admin_task(client, headers, caller_id=caller_id)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_CALLER"


def test_admin_can_delete_failed_task(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_cancelled_task_with_orphan_file(tmp_path, monkeypatch)

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.execute(
        "UPDATE tasks SET status = ?, error = ? WHERE task_id = ?",
        ("failed", "parse failed", task_id),
    )

    response = client.delete(f"/admin/tasks/{task_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Task deleted"
    assert db.get_task(task_id) is None


def test_admin_delete_rejects_processing_task(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    task_id = _make_task_with_postprocess_artifact(tmp_path, monkeypatch)

    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("processing", task_id))

    response = client.delete(f"/admin/tasks/{task_id}", headers=headers)
    assert response.status_code == 409
    body = response.json()["detail"]
    assert body["error"] == "TASK_NOT_TERMINAL"
    assert body["message"] == "Task is still running"
    assert db.get_task(task_id) is not None
