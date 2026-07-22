"""公开 REST API 后处理端点契约测试（plans 列表 / runs 触发、查询、取消）。"""

import uuid

from fastapi.testclient import TestClient
from unittest.mock import patch

from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services import reset_task_service
from mineru_mcp.task_queue import TaskDatabase


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_id="test-user",
        principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER,
        display_name="Test User",
        caller_id="test-user",
    )


def _setup(tmp_path, monkeypatch, *, configure_llm: bool = True):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    if configure_llm:
        monkeypatch.setenv("MINERU_TITLE_API_KEY", "sk-dummy")
        monkeypatch.setenv("MINERU_TITLE_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("MINERU_TITLE_MODEL", "test-model")
    reset_config()
    reset_task_service()
    return TestClient(create_api_app())


def _seed_plan(db, plan_id="ppp-1"):
    db.create_postprocess_action(
        action_id="ppa-1", name="清洗",
        config={"prompt": "清洗文本", "output_filename": "clean.md", "context_size": None},
        enabled=True,
    )
    db.create_postprocess_action(
        action_id="ppa-2", name="摘要",
        config={"prompt": "生成摘要", "output_filename": "summary.md", "context_size": None},
        enabled=True,
    )
    db.create_postprocess_plan(
        plan_id=plan_id, title="清洗+摘要",
        steps=[{"action_id": "ppa-1"}, {"action_id": "ppa-2"}],
        enabled=True,
    )


def _make_completed_task(tmp_path, db, owner_id="test-user"):
    task_id = uuid.uuid4().hex
    task_dir = tmp_path / f"task-{task_id[:8]}"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (task_dir / "input.pdf").write_bytes(b"%PDF-fake")
    (output_dir / "input.md").write_text("# 原文\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    db.create_task(
        task_id=task_id, task_dir=str(task_dir),
        input_filename="input.pdf", backend="pipeline", owner_id=owner_id,
    )
    db.execute("UPDATE tasks SET status = 'completed' WHERE task_id = ?", (task_id,))
    return task_id


def test_list_plans_public(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_plan(db)

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.get("/postprocess-plans")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["plan_id"] == "ppp-1"
    assert items[0]["title"] == "清洗+摘要"
    assert [s["name"] for s in items[0]["steps"]] == ["清洗", "摘要"]


def test_create_list_and_cancel_run_public(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_plan(db)
    task_id = _make_completed_task(tmp_path, db)

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        # 触发
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={"plan_id": "ppp-1"})
        assert response.status_code == 200
        run = response.json()["run"]
        run_id = run["run_id"]
        assert run["status"] == "pending"
        assert run["trigger_source"] == "manual"
        assert len(run["steps"]) == 2
        assert run["plan_title"] == "清洗+摘要"

        # 查询
        response = client.get(f"/tasks/{task_id}/postprocess-runs")
        assert response.status_code == 200
        runs = response.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id

        # 取消
        response = client.post(f"/postprocess-runs/{run_id}/cancel")
        assert response.status_code == 200
        assert response.json()["cancelled"] is True
        assert response.json()["run"]["status"] == "cancelled"

        # 终态再取消 → 409
        response = client.post(f"/postprocess-runs/{run_id}/cancel")
        assert response.status_code == 409


def test_create_run_rejects_missing_plan_id(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id = _make_completed_task(tmp_path, db)

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_POSTPROCESS_PLAN"


def test_create_run_rejects_unknown_plan(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id = _make_completed_task(tmp_path, db)

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={"plan_id": "ppp-missing"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_POSTPROCESS_PLAN"


def test_create_run_rejects_non_completed_task(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_plan(db)
    task_id = _make_completed_task(tmp_path, db)
    db.execute("UPDATE tasks SET status = 'processing' WHERE task_id = ?", (task_id,))

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={"plan_id": "ppp-1"})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "TASK_NOT_COMPLETED"


def test_create_run_rejects_unconfigured_llm(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch, configure_llm=False)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_plan(db)
    task_id = _make_completed_task(tmp_path, db)

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={"plan_id": "ppp-1"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "POSTPROCESS_LLM_NOT_CONFIGURED"
    assert "configuration is incomplete" in response.json()["detail"]["message"]


def test_run_endpoints_hide_tasks_of_other_owners(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _seed_plan(db)
    task_id = _make_completed_task(tmp_path, db, owner_id="someone-else")

    with patch("mineru_mcp.api.get_principal_from_request", return_value=_principal()):
        response = client.post(f"/tasks/{task_id}/postprocess-runs", json={"plan_id": "ppp-1"})
        assert response.status_code == 404

        response = client.get(f"/tasks/{task_id}/postprocess-runs")
        assert response.status_code == 404
