import base64
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mineru_mcp.auth import (
    AuthMode,
    auth_invalid,
    auth_missing,
    check_auth_header,
    get_auth_mode,
    resolve_principal,
    reset_auth_config,
)
from mineru_mcp.validation import ValidationError
from mineru_mcp.errors import MCPError
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.task_queue import FileManager, TaskDatabase
from mineru_mcp.services.task_service import TaskService
from mineru_mcp.config import MCPConfig, reset_config


def _minimal_pdf_base64() -> str:
    minimal = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n%%EOF"
    )
    return base64.b64encode(minimal).decode()


def _setup_temp_env(tmp_path):
    os.environ["MINERU_OUTPUT_ROOT"] = str(tmp_path / "output")
    os.environ["MINERU_DB_PATH"] = str(tmp_path / "output" / "tasks.db")
    reset_auth_config()
    reset_config()
    return TaskDatabase(db_path=os.environ["MINERU_DB_PATH"])


def _create_caller(db: TaskDatabase, caller_id: str, name: str, api_key: str):
    db.create_caller(
        caller_id=caller_id,
        name=name,
        api_key=api_key,
        api_key_prefix=api_key[:4],
        api_key_suffix=api_key[-4:],
    )


class TestDatabaseApiKeyAuth:
    def test_auth_mode_is_database_api_key(self):
        reset_auth_config()
        assert get_auth_mode() == AuthMode.DATABASE_API_KEY

    def test_missing_token_rejected(self, tmp_path):
        _setup_temp_env(tmp_path)
        error = check_auth_header(None)
        assert error is not None
        assert error.code == auth_missing().code

    def test_unknown_token_rejected(self, tmp_path):
        _setup_temp_env(tmp_path)
        error = check_auth_header("Bearer unknown-token")
        assert error is not None
        assert error.code == auth_invalid().code

    def test_valid_token_resolves_caller_principal(self, tmp_path):
        db = _setup_temp_env(tmp_path)
        _create_caller(db, "caller-a", "Caller A", "caller-token-a")

        principal = resolve_principal("Bearer caller-token-a")
        assert principal.principal_id == "caller-a"
        assert principal.caller_id == "caller-a"
        assert principal.principal_type == PrincipalType.API_KEY
        assert principal.role == PrincipalRole.USER

    def test_disabled_token_rejected(self, tmp_path):
        db = _setup_temp_env(tmp_path)
        _create_caller(db, "caller-disabled", "Caller Disabled", "caller-token-disabled")
        db.update_caller("caller-disabled", disabled=True)

        with pytest.raises(MCPError):
            resolve_principal("Bearer caller-token-disabled")


class TestTaskOwnership:
    @pytest.fixture
    def task_service(self, tmp_path):
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

    @pytest.fixture
    def user_a(self):
        return CurrentPrincipal(
            principal_id="user-a",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
            display_name="User A",
            caller_id="user-a",
        )

    @pytest.fixture
    def user_b(self):
        return CurrentPrincipal(
            principal_id="user-b",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
            display_name="User B",
            caller_id="user-b",
        )

    @pytest.fixture
    def admin(self):
        return CurrentPrincipal(
            principal_id="admin",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.ADMIN,
            display_name="Admin",
        )

    def test_user_can_create_and_get_own_task(self, task_service, user_a):
        result = task_service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(),
            file_name="test.pdf",
            principal=user_a,
        )
        assert result["status"] == "submitted"
        task_id = result["task_id"]

        status = task_service.get_task_status_authorized(task_id, user_a)
        assert status["status"] != "not_found"

    def test_user_b_cannot_see_user_a_task(self, task_service, user_a, user_b):
        result = task_service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(),
            file_name="a-task.pdf",
            principal=user_a,
        )
        task_id = result["task_id"]

        status = task_service.get_task_status_authorized(task_id, user_b)
        assert status["status"] == "not_found"

    def test_admin_can_see_all_tasks(self, task_service, user_a, admin):
        result = task_service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(),
            file_name="for-admin.pdf",
            principal=user_a,
        )
        task_id = result["task_id"]

        status = task_service.get_task_status_authorized(task_id, admin)
        assert status["status"] != "not_found"

    def test_create_task_requires_principal(self, task_service):
        with pytest.raises(ValueError, match="principal is required"):
            task_service.create_task_from_base64(
                file_base64=_minimal_pdf_base64(),
                file_name="no-principal.pdf",
                principal=None,
            )

    def test_http_backend_requires_server_url(self, task_service, user_a):
        with pytest.raises(ValidationError, match="requires a VLM server URL"):
            task_service.create_task_from_base64(
                file_base64=_minimal_pdf_base64(),
                file_name="http-missing-url.pdf",
                backend="hybrid-http-client",
                principal=user_a,
            )

    def test_local_backend_rejects_server_url(self, task_service, user_a):
        with pytest.raises(ValidationError, match="does not support a VLM server URL"):
            task_service.create_task_from_base64(
                file_base64=_minimal_pdf_base64(),
                file_name="local-with-url.pdf",
                backend="hybrid-auto-engine",
                server_url="http://localhost:30000/v1",
                principal=user_a,
            )

    def test_http_backend_uses_configured_default_server_url(self, tmp_path, user_a):
        db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
        fm = FileManager(output_root=str(tmp_path / "output"))
        config = MCPConfig(
            default_backend="hybrid-http-client",
            vlm_base_url="http://configured-vlm:30000/v1",
            vlm_api_key=None,
            vlm_model=None,
            vlm_max_concurrency=2,
            title_api_key=None,
            title_base_url=None,
            title_model=None,
            server_name="test",
            server_mode="http",
            http_host="127.0.0.1",
            http_port=8002,
            log_level="INFO",
            max_concurrent=1,
            task_timeout=123,
            retry_limit=3,
            cleanup_days=30,
            db_path=str(tmp_path / "tasks.db"),
            output_root=str(tmp_path / "output"),
        )
        svc = TaskService(db=db, file_manager=fm, config=config)

        result = svc.create_task_from_base64(
            file_base64=_minimal_pdf_base64(),
            file_name="uses-default-vlm.pdf",
            principal=user_a,
        )

        task = db.get_task(result["task_id"])
        assert task["server_url"] == "http://configured-vlm:30000/v1"
        assert task["timeout_seconds"] == 123


class TestUploadOwnership:
    @pytest.fixture
    def task_service(self, tmp_path):
        db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
        fm = FileManager(output_root=str(tmp_path / "output"))
        config = MCPConfig(
            default_backend="pipeline",
            vlm_base_url=None,
            vlm_api_key=None,
            vlm_model=None,
            vlm_max_concurrency=2,
            title_api_key=None,
            title_base_url=None,
            title_model=None,
            server_name="test",
            server_mode="http",
            http_host="127.0.0.1",
            http_port=8002,
            log_level="INFO",
            max_concurrent=1,
            task_timeout=3600,
            retry_limit=3,
            cleanup_days=30,
            db_path=str(tmp_path / "tasks.db"),
            output_root=str(tmp_path / "output"),
        )
        return TaskService(db=db, file_manager=fm, config=config)

    @pytest.fixture
    def user_a(self):
        return CurrentPrincipal(
            principal_id="upload-user-a",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
        )

    @pytest.fixture
    def user_b(self):
        return CurrentPrincipal(
            principal_id="upload-user-b",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
        )

class TestRestProtocolAuth:
    @pytest.fixture
    def rest_client(self, tmp_path):
        db_path = tmp_path / "tasks.db"
        output_root = tmp_path / "output"
        os.environ["MINERU_DB_PATH"] = str(db_path)
        os.environ["MINERU_OUTPUT_ROOT"] = str(output_root)
        os.environ["MINERU_DEFAULT_BACKEND"] = "pipeline"
        reset_auth_config()
        reset_config()

        from mineru_mcp.api import create_api_app
        from starlette.testclient import TestClient
        from mineru_mcp.services import task_service as ts_mod

        app = create_api_app()
        db = TaskDatabase(db_path=str(db_path))
        fm = FileManager(output_root=str(output_root))
        svc = TaskService(db=db, file_manager=fm)
        ts_mod.reset_task_service()
        reset_config()
        client = TestClient(app)
        yield client, svc

    @pytest.fixture
    def user_a(self):
        return CurrentPrincipal(
            principal_id="rest-user-a",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
            display_name="REST User A",
        )

    @pytest.fixture
    def user_b(self):
        return CurrentPrincipal(
            principal_id="rest-user-b",
            principal_type=PrincipalType.API_KEY,
            role=PrincipalRole.USER,
            display_name="REST User B",
        )

    def _create_task(self, svc, owner: CurrentPrincipal) -> str:
        result = svc.create_task_from_base64(
            file_base64=_minimal_pdf_base64(),
            file_name="rest-test.pdf",
            principal=owner,
        )
        assert result["status"] == "submitted"
        return result["task_id"]

    def test_unauthorized_user_gets_404_on_task_status(self, rest_client, user_a, user_b):
        client, svc = rest_client
        task_id = self._create_task(svc, user_a)

        with patch("mineru_mcp.api.get_principal_from_request", return_value=user_b):
            resp = client.get(f"/tasks/{task_id}")
            assert resp.status_code == 404

    def test_owner_gets_200_on_own_task(self, rest_client, user_a):
        client, svc = rest_client
        task_id = self._create_task(svc, user_a)

        with patch("mineru_mcp.api.get_principal_from_request", return_value=user_a):
            resp = client.get(f"/tasks/{task_id}")
            assert resp.status_code == 200


class TestTaskProcessorTimeoutBehavior:
    def test_processor_uses_task_timeout_from_scheduler_not_fixed_wait(self, tmp_path, monkeypatch):
        from mineru_mcp.task_queue.processor import TaskProcessor

        db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
        input_file = tmp_path / "input.pdf"
        input_file.write_bytes(b"%PDF-1.4\nmock")

        db.create_task(
            task_id="task-timeout",
            task_dir=str(tmp_path),
            input_filename="input.pdf",
            backend="pipeline",
            timeout_seconds=42,
        )
        db.update_status("task-timeout", "processing", progress=0, message="Starting")

        proc_instance = TaskProcessor(db=db, max_concurrent=1)

        class FakeProc:
            def __init__(self):
                self.returncode = 0

            async def communicate(self, input=None):
                return (b"DONE", b"")

        async def fake_subprocess_exec(*args, **kwargs):
            return FakeProc()

        monkeypatch.setattr("mineru_mcp.task_queue.processor.is_mineru_available", lambda: True)
        monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess_exec)
        monkeypatch.setattr(
            "mineru_mcp.task_queue.processor.FileManager.get_output_files",
            lambda self, task_dir, input_filename, backend: {"md": "out.md"},
        )
        monkeypatch.setattr(
            "mineru_mcp.task_queue.processor.FileManager.validate_task_outputs",
            lambda self, task_dir, input_filename, backend: {
                "required_missing": [],
                "recommended_missing": [],
                "optional_missing": [],
            },
        )

        task_data = db.get_task("task-timeout")
        asyncio.run(proc_instance._process_internal("task-timeout", task_data))

        task = db.get_task("task-timeout")
        assert task["status"] == "completed"
