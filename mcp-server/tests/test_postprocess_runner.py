"""PostprocessRunner（三层模型执行器）单元测试。

覆盖：v11 迁移、plan 快照解析、串联执行、失败短路、取消、覆盖写、
重启恢复、deliverable 产物聚合。
"""

import asyncio
import threading
import uuid
from pathlib import Path

import pytest

from mineru_mcp.config import MCPConfig, reset_config
from mineru_mcp.postprocess import PostprocessCancelledError, TitleLLMPostprocessor
from mineru_mcp.services.task_service import TaskService, collect_postprocess_filenames
from mineru_mcp.task_queue import FileManager, PostprocessRunner, TaskDatabase
from mineru_mcp.task_queue.postprocess_runner import build_plan_steps_snapshot


def _test_config(tmp_path: Path) -> MCPConfig:
    return MCPConfig(
        default_backend="pipeline",
        vlm_base_url=None, vlm_api_key=None, vlm_model=None,
        vlm_max_concurrency=2,
        title_api_key="sk-dummy",
        title_base_url="https://api.example.com/v1",
        title_model="test-model",
        postprocess_context_size=131072,
        postprocess_max_concurrent=2,
        server_name="test", server_mode="http",
        http_host="127.0.0.1", http_port=8002,
        log_level="INFO",
        max_concurrent=1, task_timeout=3600,
        retry_limit=3, cleanup_days=30,
        db_path=str(tmp_path / "tasks.db"),
        output_root=str(tmp_path / "output"),
    )


def _make_task(tmp_path, db, *, filename="input.pdf", backend="pipeline"):
    """创建带解析产物的完成任务。"""
    task_id = uuid.uuid4().hex
    task_dir = tmp_path / f"task-{task_id[:8]}"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / filename).write_bytes(b"%PDF-fake")
    (output_dir / "input.md").write_text("# original\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    db.create_task(
        task_id=task_id, task_dir=str(task_dir),
        input_filename=filename, backend=backend,
        enable_postprocess=False,
    )
    db.execute("UPDATE tasks SET status = 'completed' WHERE task_id = ?", (task_id,))
    return task_id, task_dir


def _add_action(db, action_id, name, prompt, output_filename):
    db.create_postprocess_action(
        action_id=action_id,
        name=name,
        config={"prompt": prompt, "output_filename": output_filename, "context_size": None},
        enabled=True,
    )


def _ok_llm(self, markdown_text, prompt, context_size=None, cancel_event=None):
    return (f"# processed by [{prompt}]\n", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})


async def _run_to_completion(db, runner, run_id):
    assert db.claim_postprocess_run(run_id)
    await runner._execute_run(run_id)


# ========== v11 迁移 ==========


def test_migrate_v11_moves_rules_into_actions_and_plans(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    # 模拟 v10 时代的 rules 数据（rules 表 CRUD 已下线，直接写 SQL）
    with db._conn() as conn:
        conn.execute(
            """
            INSERT INTO postprocess_rules (rule_id, title, prompt, output_filename, enabled, created_at, updated_at)
            VALUES ('ppr-legacy', '标题优化', '优化标题', 'post.md', 1, '2026-01-01', '2026-01-01')
            """
        )
        db._migrate_v11(conn)

    action = db.get_postprocess_action("ppr-legacy")
    assert action is not None
    assert action["name"] == "标题优化"
    assert action["type"] == "llm_transform"
    assert action["config"]["prompt"] == "优化标题"
    assert action["config"]["output_filename"] == "post.md"

    plan = db.get_postprocess_plan("ppr-legacy")
    assert plan is not None
    assert plan["title"] == "标题优化"
    assert plan["steps"] == [{"action_id": "ppr-legacy", "output_filename": None}]

    # 幂等：再次执行不报错不重复
    with db._conn() as conn:
        db._migrate_v11(conn)
    assert len(db.list_postprocess_actions()) == 1
    assert len(db.list_postprocess_plans()) == 1


# ========== 快照解析 ==========


def test_snapshot_rejects_unknown_plan(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    with pytest.raises(ValueError, match="not found"):
        build_plan_steps_snapshot(db, "ppp-missing")


def test_snapshot_rejects_disabled_plan(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _add_action(db, "ppa-1", "A", "p", "a.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=False)
    with pytest.raises(ValueError, match="disabled"):
        build_plan_steps_snapshot(db, "ppp-1")


def test_snapshot_rejects_plan_without_steps(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[], enabled=True)
    with pytest.raises(ValueError, match="no steps"):
        build_plan_steps_snapshot(db, "ppp-1")


def test_snapshot_rejects_disabled_action(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _add_action(db, "ppa-1", "A", "p", "a.md")
    db.update_postprocess_action("ppa-1", enabled=False)
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=True)
    with pytest.raises(ValueError, match="disabled"):
        build_plan_steps_snapshot(db, "ppp-1")


def test_snapshot_step_output_filename_overrides_action(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    _add_action(db, "ppa-1", "A", "p", "a.md")
    db.create_postprocess_plan(
        plan_id="ppp-1", title="P",
        steps=[{"action_id": "ppa-1", "output_filename": "override"}],
        enabled=True,
    )
    steps = build_plan_steps_snapshot(db, "ppp-1", default_context_size=4096)
    assert steps[0]["output_filename"] == "override.md"
    assert steps[0]["context_size"] == 4096


# ========== 串联执行 ==========


async def test_two_step_pipeline_chains_output(tmp_path, monkeypatch):
    """第 2 步的输入必须是第 1 步的输出。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, task_dir = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "第一步", "step1", "s1.md")
    _add_action(db, "ppa-2", "第二步", "step2", "s2.md")
    db.create_postprocess_plan(
        plan_id="ppp-1", title="两步流水线",
        steps=[{"action_id": "ppa-1"}, {"action_id": "ppa-2"}],
        enabled=True,
    )

    seen_inputs = []

    def _recording_llm(self, markdown_text, prompt, context_size=None, cancel_event=None):
        seen_inputs.append((prompt, markdown_text))
        return (f"# out of {prompt}\n", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})

    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _recording_llm)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    run_id = runner.create_run(task_id, "ppp-1", trigger_source="manual")
    await _run_to_completion(db, runner, run_id)

    run = db.get_postprocess_run(run_id)
    assert run["status"] == "completed"
    assert [r["status"] for r in run["step_results"]] == ["completed", "completed"]

    # 第 1 步读原始 md；第 2 步读第 1 步产物
    assert seen_inputs[0] == ("step1", "# original\n")
    assert seen_inputs[1] == ("step2", "# out of step1\n")

    s1 = task_dir / "input" / "auto" / "s1.md"
    s2 = task_dir / "input" / "auto" / "s2.md"
    assert s1.read_text(encoding="utf-8") == "# out of step1\n"
    assert s2.read_text(encoding="utf-8") == "# out of step2\n"


async def test_pipeline_failure_short_circuits(tmp_path, monkeypatch):
    """第 1 步失败 → run failed，第 2 步 skipped 且不产生产物。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, task_dir = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "第一步", "step1", "s1.md")
    _add_action(db, "ppa-2", "第二步", "step2", "s2.md")
    db.create_postprocess_plan(
        plan_id="ppp-1", title="两步流水线",
        steps=[{"action_id": "ppa-1"}, {"action_id": "ppa-2"}],
        enabled=True,
    )

    def _boom(self, markdown_text, prompt, context_size=None, cancel_event=None):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _boom)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    run_id = runner.create_run(task_id, "ppp-1")
    await _run_to_completion(db, runner, run_id)

    run = db.get_postprocess_run(run_id)
    assert run["status"] == "failed"
    assert "LLM down" in run["error"]
    statuses = [r["status"] for r in run["step_results"]]
    assert statuses == ["failed", "skipped"]
    assert not (task_dir / "input" / "auto" / "s1.md").exists()
    assert not (task_dir / "input" / "auto" / "s2.md").exists()


async def test_cancel_run_marks_cancelled(tmp_path, monkeypatch):
    """执行中取消：run cancelled，未完成步骤 skipped。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, _ = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "第一步", "step1", "s1.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=True)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))

    def _cancel_during(self, markdown_text, prompt, context_size=None, cancel_event=None):
        cancel_event.set()
        raise PostprocessCancelledError("cancelled mid-chunk")

    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _cancel_during)

    run_id = runner.create_run(task_id, "ppp-1")
    assert db.claim_postprocess_run(run_id)
    await runner._execute_run(run_id)

    run = db.get_postprocess_run(run_id)
    assert run["status"] == "cancelled"
    assert run["step_results"][0]["status"] == "cancelled"


def test_cancel_pending_run_via_runner(tmp_path):
    """pending 的 run 直接 CAS 取消。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, _ = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "A", "p", "a.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=True)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    run_id = runner.create_run(task_id, "ppp-1")
    assert runner.cancel_run(run_id)
    assert db.get_postprocess_run(run_id)["status"] == "cancelled"
    # 终态不可再取消
    assert not runner.cancel_run(run_id)


async def test_rerun_overwrites_same_filename(tmp_path, monkeypatch):
    """重跑同一 plan：同名产物被覆盖（幂等）。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, task_dir = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "A", "p", "out.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=True)

    version = {"n": 0}

    def _versioned_llm(self, markdown_text, prompt, context_size=None, cancel_event=None):
        version["n"] += 1
        return (f"# version {version['n']}\n", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})

    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _versioned_llm)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    await _run_to_completion(db, runner, runner.create_run(task_id, "ppp-1"))
    await _run_to_completion(db, runner, runner.create_run(task_id, "ppp-1"))

    output = task_dir / "input" / "auto" / "out.md"
    assert output.read_text(encoding="utf-8") == "# version 2\n"
    runs = db.list_postprocess_runs(task_id=task_id)
    assert len(runs) == 2
    assert all(r["status"] == "completed" for r in runs)


def test_reset_running_runs_for_recovery(tmp_path):
    """重启恢复：running → pending。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, _ = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "A", "p", "a.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P", steps=[{"action_id": "ppa-1"}], enabled=True)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    run_id = runner.create_run(task_id, "ppp-1")
    assert db.claim_postprocess_run(run_id)
    assert db.get_postprocess_run(run_id)["status"] == "running"

    recovered = db.reset_running_postprocess_runs()
    assert recovered == 1
    assert db.get_postprocess_run(run_id)["status"] == "pending"


def test_create_run_rejects_unknown_task(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    with pytest.raises(ValueError, match="not found"):
        runner.create_run("task-missing", "ppp-1")


# ========== deliverable 聚合 ==========


def test_collect_filenames_aggregates_runs_and_legacy(tmp_path):
    """多 run 的产物文件名全部聚合；历史列兜底。"""
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, _ = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "A", "p", "a.md")
    _add_action(db, "ppa-2", "B", "p", "b.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P1", steps=[{"action_id": "ppa-1"}], enabled=True)
    db.create_postprocess_plan(plan_id="ppp-2", title="P2", steps=[{"action_id": "ppa-2"}], enabled=True)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))
    runner.create_run(task_id, "ppp-1")
    runner.create_run(task_id, "ppp-2")

    task = db.get_task(task_id)
    names = collect_postprocess_filenames(db, task)
    assert names == ["a.md", "b.md"]

    # 历史任务：无 run 但 tasks 列有冻结文件名 → 兜底可见
    db.execute("UPDATE tasks SET postprocess_output_filename = ? WHERE task_id = ?", ("legacy.md", task_id))
    task = db.get_task(task_id)
    names = collect_postprocess_filenames(db, task)
    assert names == ["a.md", "b.md", "legacy.md"]


def test_list_deliverables_includes_all_run_artifacts(tmp_path, monkeypatch):
    """两个不同方案的 run 产物都出现在 list_deliverables。"""
    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _ok_llm)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    task_id, _ = _make_task(tmp_path, db)
    _add_action(db, "ppa-1", "A", "p", "a.md")
    _add_action(db, "ppa-2", "B", "p", "b.md")
    db.create_postprocess_plan(plan_id="ppp-1", title="P1", steps=[{"action_id": "ppa-1"}], enabled=True)
    db.create_postprocess_plan(plan_id="ppp-2", title="P2", steps=[{"action_id": "ppa-2"}], enabled=True)

    runner = PostprocessRunner(db=db, config=_test_config(tmp_path))

    async def _run_both():
        await _run_to_completion(db, runner, runner.create_run(task_id, "ppp-1"))
        await _run_to_completion(db, runner, runner.create_run(task_id, "ppp-2"))

    asyncio.run(_run_both())

    service = TaskService(db=db, file_manager=FileManager(output_root=str(tmp_path)), config=_test_config(tmp_path))
    result = service.list_deliverables(task_id)
    postprocess_names = [
        a["filename"] for a in result["artifacts"] if a["artifact_type"] == "postprocessed_markdown"
    ]
    assert postprocess_names == ["a.md", "b.md"]
