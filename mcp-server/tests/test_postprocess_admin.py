"""Admin-level regression tests for postprocess rules (M3) and downloads (H2)."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from mineru_mcp.admin_auth import init_default_admin, get_default_admin_password
from mineru_mcp.api import create_api_app
from mineru_mcp.config import reset_config
from mineru_mcp.task_queue import TaskDatabase


def _setup_admin_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("MINERU_ADMIN_INITIAL_PASSWORD", "Admin123!")
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


def _create_rule(client, headers, title="测试方案") -> str:
    response = client.post(
        "/admin/postprocess-rules",
        json={"title": title, "prompt": "清洗文本", "output_filename": "final.md"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["rule_id"]


def _create_caller_with_default_rule(client, headers, rule_id: str) -> str:
    response = client.post(
        "/admin/callers",
        json={"name": "caller-a", "default_postprocess_rule_id": rule_id},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["caller_id"]


# ========== M3: caller reference guards on delete/disable ==========


def test_delete_rule_referenced_by_caller_returns_409(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    rule_id = _create_rule(client, headers)
    caller_id = _create_caller_with_default_rule(client, headers, rule_id)

    response = client.delete(f"/admin/postprocess-rules/{rule_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "RULE_REFERENCED_BY_CALLERS"

    # Clearing the caller default releases the rule.
    clear = client.patch(
        f"/admin/callers/{caller_id}",
        json={"default_postprocess_rule_id": ""},
        headers=headers,
    )
    assert clear.status_code == 200

    response = client.delete(f"/admin/postprocess-rules/{rule_id}", headers=headers)
    assert response.status_code == 200


def test_disable_rule_referenced_by_caller_returns_409(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    rule_id = _create_rule(client, headers)
    _create_caller_with_default_rule(client, headers, rule_id)

    response = client.put(
        f"/admin/postprocess-rules/{rule_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "RULE_REFERENCED_BY_CALLERS"

    # Updates that do not disable the rule remain allowed.
    response = client.put(
        f"/admin/postprocess-rules/{rule_id}",
        json={"title": "改名"},
        headers=headers,
    )
    assert response.status_code == 200


def test_delete_unreferenced_rule_succeeds(tmp_path, monkeypatch):
    client, headers = _setup_admin_client(tmp_path, monkeypatch)
    rule_id = _create_rule(client, headers)

    response = client.delete(f"/admin/postprocess-rules/{rule_id}", headers=headers)
    assert response.status_code == 200


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
