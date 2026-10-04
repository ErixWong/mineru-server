import sqlite3

from fastapi.testclient import TestClient

from mineru_mcp.admin_auth import get_default_admin_password, init_default_admin
from mineru_mcp.app import create_unified_app
from mineru_mcp.auth import resolve_principal
from mineru_mcp.caller_key_crypto import generate_master_key
from mineru_mcp.config import reset_config
from mineru_mcp.services import reset_task_service
from mineru_mcp.task_queue import TaskDatabase


def _setup(tmp_path, monkeypatch):
    output_root = tmp_path / "output"
    db_path = output_root / "tasks.db"
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("MINERU_DB_PATH", str(db_path))
    monkeypatch.setenv("MINERU_CALLER_KEY_MASTER_KEY", generate_master_key())
    monkeypatch.setenv("MINERU_DEFAULT_BACKEND", "pipeline")
    reset_config()
    reset_task_service()
    db = TaskDatabase(db_path=str(db_path))
    init_default_admin()
    db.set_admin_password_change_required("admin", False)
    return db, TestClient(create_unified_app(enable_api=True, enable_mcp=False))


def _admin_login(client):
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": get_default_admin_password()},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response.cookies["admin_csrf"]


def _create_user(client, csrf, *, username="portal-user", password="Portal123!"):
    response = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "password": password,
            "display_name": "Portal User",
        },
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _user_login(client, username="portal-user", password="Portal123!"):
    response = client.post(
        "/api/admin/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "user"
    return response


def test_admin_user_creation_links_encrypted_api_key_and_preserves_legacy_callers(tmp_path, monkeypatch):
    db, client = _setup(tmp_path, monkeypatch)
    db.create_caller(
        caller_id="legacy-caller",
        name="Legacy",
        api_key="legacy-api-key",
        api_key_prefix="legacy-a",
        api_key_suffix="key",
    )

    csrf = _admin_login(client)
    created = _create_user(client, csrf)
    caller = db.fetch_one(
        "SELECT user_id, quota_total_pages, api_key_encrypted FROM callers WHERE caller_id = ?",
        (created["caller_id"],),
    )
    assert caller["user_id"] == created["user_id"]
    assert caller["quota_total_pages"] is None
    assert caller["api_key_encrypted"] != created["api_key"]
    assert db.get_caller_by_api_key(created["api_key"])["caller_id"] == created["caller_id"]

    principal = resolve_principal(f"Bearer {created['api_key']}")
    assert principal.principal_id == created["user_id"]
    assert principal.user_id == created["user_id"]
    assert principal.caller_id == created["caller_id"]
    assert resolve_principal("Bearer legacy-api-key").principal_id == "legacy-caller"
    assert db.get_quota_balance("legacy-caller") is None
    assert client.get("/api/tasks", headers={"Authorization": f"Bearer {created['api_key']}"}).status_code == 200


def test_user_login_portal_balance_ownership_and_admin_access_denial(tmp_path, monkeypatch):
    db, admin_client = _setup(tmp_path, monkeypatch)
    csrf = _admin_login(admin_client)
    alice = _create_user(admin_client, csrf, username="alice")
    bob = _create_user(admin_client, csrf, username="bob")
    alice_caller = db.get_user_caller(alice["user_id"])
    bob_caller = db.get_user_caller(bob["user_id"])

    db.execute(
        """
        UPDATE callers SET quota_total_pages = 30
        WHERE caller_id = ?
        """,
        (alice_caller["caller_id"],),
    )
    db.execute(
        """
        INSERT INTO quota_ledger (ledger_id, caller_id, delta, reason, balance_after)
        VALUES ('alice-reservation', ?, -7, 'task_reservation', 23)
        """,
        (alice_caller["caller_id"],),
    )
    db.create_task(
        task_id="alice-task",
        task_dir=str(tmp_path / "alice-task"),
        input_filename="alice.pdf",
        owner_id=alice["user_id"],
        owner_type="api_key",
        caller_id=alice_caller["caller_id"],
    )
    db.create_task(
        task_id="bob-task",
        task_dir=str(tmp_path / "bob-task"),
        input_filename="bob.pdf",
        owner_id=bob["user_id"],
        owner_type="api_key",
        caller_id=bob_caller["caller_id"],
    )

    alice_client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    _user_login(alice_client, username="alice")
    me = alice_client.get("/api/portal/me")
    assert me.status_code == 200
    assert me.json()["quota_total_pages"] == 30
    assert me.json()["quota_used_pages"] == 7
    assert me.json()["quota_remaining_pages"] == 23

    ledger = alice_client.get("/api/portal/quota/ledger")
    assert ledger.status_code == 200
    assert ledger.json()["items"][0]["delta"] == -7
    tasks = alice_client.get("/api/portal/tasks")
    assert tasks.status_code == 200
    assert [task["task_id"] for task in tasks.json()["tasks"]] == ["alice-task"]
    assert alice_client.get("/api/portal/tasks/alice-task").status_code == 200
    denied_task = alice_client.get("/api/portal/tasks/bob-task")
    assert denied_task.status_code == 404
    denied_admin = alice_client.get("/api/admin/users")
    assert denied_admin.status_code == 403
    assert denied_admin.json()["detail"]["error"] == "FORBIDDEN"


def test_admin_top_up_records_ledger_and_rest_task_submit_reserves_pages(tmp_path, monkeypatch):
    db, client = _setup(tmp_path, monkeypatch)
    csrf = _admin_login(client)
    user = _create_user(client, csrf)

    top_up = client.post(
        f"/api/admin/users/{user['user_id']}/quota",
        json={"pages": 2, "reason": "initial package"},
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert top_up.status_code == 200, top_up.text
    assert top_up.json()["balance_after"] == 2
    ledger = client.get(f"/api/admin/users/{user['user_id']}/quota/ledger")
    assert ledger.status_code == 200
    assert ledger.json()["items"][0]["reason"] == "initial package"

    portal_client = TestClient(create_unified_app(enable_api=True, enable_mcp=False))
    _user_login(portal_client)
    assert portal_client.get("/api/portal/me").json()["quota_remaining_pages"] == 2

    submitted = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {user['api_key']}"},
        data={"backend": "pipeline"},
        files={"file": ("one-page.pdf", b"%PDF-1.4\nquota test input", "application/pdf")},
    )
    assert submitted.status_code == 200, submitted.text
    task = db.get_task(submitted.json()["task_id"])
    assert task["caller_id"] == user["caller_id"]
    assert task["owner_id"] == user["user_id"]
    assert task["pages_reserved"] == 1
    assert db.get_quota_balance(user["caller_id"]) == 1


def test_migration_v18_leaves_unlinked_existing_callers_usable(tmp_path, monkeypatch):
    db, _ = _setup(tmp_path, monkeypatch)
    db.create_caller(
        caller_id="unlinked-caller",
        name="Unlinked",
        api_key="unlinked-key",
        api_key_prefix="unlinke",
        api_key_suffix="key",
    )

    with sqlite3.connect(db.db_path) as conn:
        conn.execute("DROP INDEX idx_callers_user_id")
        conn.execute("ALTER TABLE callers DROP COLUMN user_id")
        conn.execute("DROP TABLE users")
        conn.execute("PRAGMA user_version = 17")

    migrated = TaskDatabase(db_path=str(db.db_path))
    assert migrated.SCHEMA_VERSION == 18
    assert migrated.get_caller_by_api_key("unlinked-key")["caller_id"] == "unlinked-caller"
    principal = resolve_principal("Bearer unlinked-key")
    assert principal.principal_id == "unlinked-caller"
    assert principal.user_id is None
    assert migrated.get_quota_balance("unlinked-caller") is None
