import asyncio
import base64
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

import mineru_mcp.postprocess as postprocess_module
from mineru_mcp.config import MCPConfig, reset_config
from mineru_mcp.postprocess import (
    PostprocessCancelledError,
    TitleLLMPostprocessor,
    build_postprocess_chunks,
    build_postprocess_output_path,
    normalize_output_filename,
)
from mineru_mcp.principal import CurrentPrincipal, PrincipalRole, PrincipalType
from mineru_mcp.services.task_service import TaskService
from mineru_mcp.task_queue import FileManager, TaskDatabase
from mineru_mcp.task_queue.processor import TaskProcessor
from mineru_mcp.validation import ValidationError


def _minimal_pdf_base64() -> str:
    minimal = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n%%EOF"
    )
    return base64.b64encode(minimal).decode()


def _test_config(tmp_path: Path) -> MCPConfig:
    return MCPConfig(
        default_backend="pipeline",
        vlm_base_url=None, vlm_api_key=None, vlm_model=None,
        vlm_max_concurrency=2,
        title_api_key="sk-dummy",
        title_base_url="https://api.example.com/v1",
        title_model="test-model",
        postprocess_context_size=131072,
        server_name="test", server_mode="http",
        http_host="127.0.0.1", http_port=8002,
        log_level="INFO",
        max_concurrent=1, task_timeout=3600,
        retry_limit=3, cleanup_days=30,
        db_path=str(tmp_path / "tasks.db"),
        output_root=str(tmp_path / "output"),
    )


def _unconfigured_config(tmp_path: Path) -> MCPConfig:
    config = _test_config(tmp_path)
    config.title_api_key = None
    config.title_base_url = None
    config.title_model = None
    return config


# ========== Postprocess unit tests ==========


def test_build_postprocess_output_path_uses_configured_filename():
    md_path = Path("D:/tmp/example.md")
    result = build_postprocess_output_path(md_path, "final-output.md")
    assert result.name == "final-output.md"


def test_build_postprocess_output_path_rejects_empty_filename():
    with pytest.raises(ValueError, match="required"):
        build_postprocess_output_path(Path("x.md"), None)


def test_normalize_output_filename_rejects_path_segments():
    assert normalize_output_filename("nested/result") == "result.md"
    assert normalize_output_filename("done") == "done.md"


def test_build_postprocess_chunks_no_overlap_on_plain_text():
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = build_postprocess_chunks(text, 10)
    result = [chunk.text for chunk in chunks]
    assert result == ["abcdefghij", "klmnopqrst", "uvwxyz"]


def test_build_postprocess_chunks_prefers_heading_boundaries():
    markdown = (
        "# Chapter 1\n\n"
        "Content of chapter 1.\n\n"
        "## 1.1 Section\n\n"
        "Section content here.\n\n"
        "# Chapter 2\n\n"
        "Content of chapter 2.\n"
    )
    chunks = build_postprocess_chunks(markdown, 60)
    assert len(chunks) >= 2
    assert chunks[0].heading_path == ["Chapter 1"]
    assert "Chapter 2" not in chunks[0].text
    assert any(chunk.heading_path == ["Chapter 2"] for chunk in chunks)


def test_build_postprocess_chunks_keeps_code_block_together_when_possible():
    """S6: code-fence block must stay whole across chunk boundaries."""
    intro = "Intro paragraph.\n\n"
    fence = "```python\nprint('hello')\nprint('world')\n```\n\n"
    outro = "Closing.\n"
    markdown = intro + fence + outro
    context = len(fence) + 2
    chunks = build_postprocess_chunks(markdown, context)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.text.count("```") % 2 == 0
    assert any("```python" in c.text and c.text.count("```") == 2 for c in chunks)


def test_build_postprocess_chunks_merges_small_heading_chunks():
    """Heading-dense docs must not explode into one LLM call per heading."""
    sections = []
    for i in range(1, 21):
        sections.append(f"{'#' * (1 + i % 3)} Section {i}\n\n" + ("body %d " % i) * 100 + "\n\n")
    markdown = "".join(sections)

    unmerged = build_postprocess_chunks(markdown, 128 * 1024, min_chunk_chars=0)
    assert len(unmerged) == 20  # one chunk per heading without merging

    merged = build_postprocess_chunks(markdown, 128 * 1024)
    assert 1 < len(merged) < 20
    # Lossless: merged chunk texts reconstruct the source exactly.
    assert "".join(chunk.text for chunk in merged) == markdown
    # Every section's heading path is still represented across the chunks.
    covered = [path for chunk in merged for path in chunk.covered_heading_paths]
    assert any(path[-1] == "Section 7" for path in covered)
    assert any(path[-1] == "Section 20" for path in covered)
    # Re-indexed sequentially after merging.
    assert [chunk.chunk_index for chunk in merged] == list(range(1, len(merged) + 1))


def test_build_postprocess_chunks_merge_respects_context_cap():
    """Merging must never grow a chunk beyond context_size."""
    sections = []
    for i in range(1, 9):
        sections.append(f"# S{i}\n\n" + "x" * 900 + "\n\n")
    markdown = "".join(sections)

    chunks = build_postprocess_chunks(markdown, 2000, min_chunk_chars=1500)
    assert all(len(chunk.text) <= 2000 for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == markdown
    assert len(chunks) >= 4  # ~910 chars/section, cap 2000 → at most 2 sections per chunk


def test_build_postprocess_chunks_merge_dedups_consecutive_paths():
    """Capacity-split chunks sharing one heading path must not repeat it."""
    markdown = "# Big\n\n" + "y" * 5000 + "\n\n# Tail\n\n" + "z" * 100 + "\n\n"
    chunks = build_postprocess_chunks(markdown, 2000, min_chunk_chars=10000)
    big_chunks = [c for c in chunks if c.covered_heading_paths and c.covered_heading_paths[0] == ["Big"]]
    for chunk in big_chunks:
        assert chunk.covered_heading_paths.count(["Big"]) == 1


# ========== Task-creation tests ==========


def test_create_task_freezes_postprocess_output_filename(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _test_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-test", title="JSON postprocess", prompt="Convert to markdown",
        output_filename="normalized-result.md", enabled=True,
    )
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="User A", caller_id="user-a",
    )
    result = service.create_task_from_base64(
        file_base64=_minimal_pdf_base64(), file_name="input.pdf",
        principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-test",
    )
    task = db.get_task(result["task_id"])
    assert task is not None
    assert task["postprocess_output_filename"] == "normalized-result.md"
    assert task["postprocess_status"] == "pending"


def test_postprocess_output_filename_no_longer_collides_with_display_stem(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _test_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-collision", title="Collision", prompt="process",
        output_filename="input.md", enabled=True,
    )
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="A", caller_id="user-a",
    )
    # Since round01 the on-disk source markdown is named {task_id[:8]}.md,
    # not input.md, so "input.md" no longer collides.  The task should
    # succeed without a VALIDATION error.
    result = service.create_task_from_base64(
        file_base64=_minimal_pdf_base64(), file_name="input.pdf",
        principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-collision",
    )
    assert result["status"] == "submitted"


def test_list_task_artifacts_exposes_generated_postprocess_filename(tmp_path):
    fm = FileManager(output_root=str(tmp_path / "output"))
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (output_dir / "input.md").write_text("# hello\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    (output_dir / "input_content_list.json").write_text("[]", encoding="utf-8")
    (output_dir / "input_content_list_v2.json").write_text("[]", encoding="utf-8")
    (output_dir / "fixed-output.md").write_text("# processed\n", encoding="utf-8")
    (output_dir / "images").mkdir()
    artifacts = fm.list_task_artifacts(
        task_dir=task_dir, input_filename="input.pdf", backend="pipeline",
        postprocess_output_filename="fixed-output.md",
    )
    postprocess_artifact = next(item for item in artifacts if item["artifact_type"] == "postprocessed_markdown")
    assert postprocess_artifact["filename"] == "fixed-output.md"
    assert postprocess_artifact["download_key"].endswith("fixed-output.md")
    assert postprocess_artifact["available"] is True


def test_create_task_inherits_default_postprocess_rule_from_caller(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _test_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-default", title="Default", prompt="process",
        output_filename="default-output.md", enabled=True,
    )
    db.create_caller(
        caller_id="caller-a", name="Caller A",
        api_key="token-a", api_key_prefix="token", api_key_suffix="en-a",
        default_postprocess_rule_id="ppr-default",
    )
    principal = CurrentPrincipal(
        principal_id="caller-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="Caller A", caller_id="caller-a",
    )
    result = service.create_task_from_base64(
        file_base64=_minimal_pdf_base64(), file_name="input.pdf", principal=principal,
    )
    task = db.get_task(result["task_id"])
    assert task is not None
    assert task["enable_postprocess"] == 1
    assert task["postprocess_rule_id"] == "ppr-default"
    assert task["postprocess_output_filename"] == "default-output.md"


def test_create_task_can_explicitly_disable_default_postprocess_rule(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _test_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-default", title="Default", prompt="process",
        output_filename="default-output.md", enabled=True,
    )
    db.create_caller(
        caller_id="caller-a", name="Caller A",
        api_key="token-a", api_key_prefix="token", api_key_suffix="en-a",
        default_postprocess_rule_id="ppr-default",
    )
    principal = CurrentPrincipal(
        principal_id="caller-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="Caller A", caller_id="caller-a",
    )
    result = service.create_task_from_base64(
        file_base64=_minimal_pdf_base64(), file_name="input.pdf",
        principal=principal, enable_postprocess=False,
    )
    task = db.get_task(result["task_id"])
    assert task is not None
    assert task["enable_postprocess"] == 0
    assert task["postprocess_rule_id"] is None
    assert task["postprocess_status"] == "not_enabled"


def test_create_task_freezes_postprocess_prompt_snapshot(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _test_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-snapshot", title="Snapshot", prompt="original prompt",
        output_filename="snapshot-output.md", enabled=True,
    )
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="A", caller_id="user-a",
    )
    result = service.create_task_from_base64(
        file_base64=_minimal_pdf_base64(), file_name="input.pdf",
        principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-snapshot",
    )
    db.update_postprocess_rule("ppr-snapshot", prompt="modified prompt", title="modified")
    task = db.get_task(result["task_id"])
    assert task is not None
    assert task["postprocess_prompt_snapshot"] == "original prompt"
    assert task["postprocess_rule_title_snapshot"] == "Snapshot"


# ========== L1: conditional artifact exposure ==========


def test_list_task_artifacts_omits_postprocess_row_without_filename(tmp_path):
    fm = FileManager(output_root=str(tmp_path / "output"))
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (output_dir / "input.md").write_text("# hello\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    (output_dir / "images").mkdir()
    artifacts = fm.list_task_artifacts(
        task_dir=task_dir, input_filename="input.pdf", backend="pipeline",
    )
    assert all(item["artifact_type"] != "postprocessed_markdown" for item in artifacts)


def test_list_task_artifacts_degrades_on_invalid_filename(tmp_path):
    """S1: a truthy-but-invalid filename skips the artifact row cleanly."""
    fm = FileManager(output_root=str(tmp_path / "output"))
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True)
    (output_dir / "input.md").write_text("# hello\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    (output_dir / "images").mkdir()
    artifacts = fm.list_task_artifacts(
        task_dir=task_dir, input_filename="input.pdf", backend="pipeline",
        postprocess_output_filename="  .  ",
    )
    assert all(item["artifact_type"] != "postprocessed_markdown" for item in artifacts)


# ========== M5: LLM call retry policy ==========


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")
    def json(self):
        return {"ok": True}


def test_llm_call_retries_transient_5xx(monkeypatch):
    monkeypatch.setattr(postprocess_module.time, "sleep", lambda _s: None)
    attempts = []
    class _Client:
        def post(self, url, headers=None, json=None):
            attempts.append(1)
            return _FakeResponse(500 if len(attempts) == 1 else 200)
    data = TitleLLMPostprocessor._call_chat_completions(_Client(), "http://x", {}, {})
    assert data == {"ok": True}
    assert len(attempts) == 2


def test_llm_call_does_not_retry_4xx(monkeypatch):
    monkeypatch.setattr(postprocess_module.time, "sleep", lambda _s: None)
    attempts = []
    class _Client:
        def post(self, url, headers=None, json=None):
            attempts.append(1)
            return _FakeResponse(400)
    with pytest.raises(RuntimeError, match="http 400"):
        TitleLLMPostprocessor._call_chat_completions(_Client(), "http://x", {}, {})
    assert len(attempts) == 1


def test_llm_call_retries_transport_errors_then_gives_up(monkeypatch):
    monkeypatch.setattr(postprocess_module.time, "sleep", lambda _s: None)
    attempts = []
    class _Client:
        def post(self, url, headers=None, json=None):
            attempts.append(1)
            raise httpx.ConnectError("boom")
    with pytest.raises(httpx.ConnectError):
        TitleLLMPostprocessor._call_chat_completions(_Client(), "http://x", {}, {})
    assert len(attempts) == postprocess_module.LLM_MAX_RETRIES + 1


def test_llm_call_does_not_retry_read_timeout(monkeypatch):
    monkeypatch.setattr(postprocess_module.time, "sleep", lambda _s: None)
    attempts = []
    class _Client:
        def post(self, url, headers=None, json=None):
            attempts.append(1)
            raise httpx.ReadTimeout("too slow")
    with pytest.raises(httpx.ReadTimeout):
        TitleLLMPostprocessor._call_chat_completions(_Client(), "http://x", {}, {})
    assert len(attempts) == 1


def test_llm_call_retries_connect_timeout(monkeypatch):
    monkeypatch.setattr(postprocess_module.time, "sleep", lambda _s: None)
    attempts = []
    class _Client:
        def post(self, url, headers=None, json=None):
            attempts.append(1)
            raise httpx.ConnectTimeout("no route")
    with pytest.raises(httpx.ConnectTimeout):
        TitleLLMPostprocessor._call_chat_completions(_Client(), "http://x", {}, {})
    assert len(attempts) == postprocess_module.LLM_MAX_RETRIES + 1


# ========== W6: task creation rejects unconfigured LLM ==========


def test_create_task_rejects_unconfigured_postprocess_llm(tmp_path):
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    config = _unconfigured_config(tmp_path)
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-test", title="test", prompt="cleanup",
        output_filename="test.md", enabled=True,
    )
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="A", caller_id="user-a",
    )
    with pytest.raises(ValidationError, match="Postprocess LLM is not configured"):
        service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(), file_name="input.pdf",
            principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-test",
        )


# ========== Processor-level tests (H1 / M1-B / M2 / W1 / W3 / S4) ==========


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
    async def communicate(self, input=None):
        return (self._stdout, self._stderr)


def _setup_processor_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_OUTPUT_ROOT", str(tmp_path / "out"))
    monkeypatch.setenv("MINERU_DB_PATH", str(tmp_path / "out" / "tasks.db"))
    reset_config()
    return TaskDatabase(db_path=str(tmp_path / "out" / "tasks.db"))


def _make_pipeline_task(tmp_path, db, *, enable_postprocess=True):
    task_id = uuid.uuid4().hex
    task_dir = tmp_path / "task"
    output_dir = task_dir / "input" / "auto"
    output_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "input.pdf").write_bytes(b"%PDF-fake")
    (output_dir / "input.md").write_text("# original\n", encoding="utf-8")
    (output_dir / "input_middle.json").write_text("{}", encoding="utf-8")
    db.create_task(
        task_id=task_id, task_dir=str(task_dir),
        input_filename="input.pdf", backend="pipeline",
        enable_postprocess=enable_postprocess,
        postprocess_rule_id="ppr-x" if enable_postprocess else None,
        postprocess_output_filename="final.md" if enable_postprocess else None,
        postprocess_rule_title_snapshot="Title" if enable_postprocess else None,
        postprocess_prompt_snapshot="Prompt" if enable_postprocess else None,
        postprocess_status="pending" if enable_postprocess else "not_enabled",
    )
    return task_id, task_dir


def _patch_subprocess(monkeypatch, proc: _FakeProc):
    import mineru_mcp.task_queue.processor as processor_module
    monkeypatch.setattr(processor_module, "is_mineru_available", lambda: True)
    async def _fake_exec(*args, **kwargs):
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)


def _patch_llm(monkeypatch, impl):
    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", impl)


def test_processor_runs_postprocess_and_completes(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    def _ok(self, markdown_text, prompt, context_size=None, cancel_event=None):
        return ("# done\n", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})
    _patch_llm(monkeypatch, _ok)
    processor = TaskProcessor(db=db, max_concurrent=1)
    asyncio.run(processor._process_internal(task_id, db.get_task(task_id)))
    task = db.get_task(task_id)
    assert task["status"] == "completed"
    assert task["postprocess_status"] == "completed"
    output = Path(task["task_dir"]) / "input" / "auto" / "final.md"
    assert output.read_text(encoding="utf-8") == "# done\n"


def test_processor_marks_postprocess_skipped_when_parse_fails(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=1, stderr=b"boom"))
    processor = TaskProcessor(db=db, max_concurrent=1)
    asyncio.run(processor._process_internal(task_id, db.get_task(task_id)))
    task = db.get_task(task_id)
    assert task["status"] == "failed"
    assert task["postprocess_status"] == "skipped"


def test_processor_marks_postprocess_failed_when_llm_fails(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    def _boom(self, markdown_text, prompt, context_size=None, cancel_event=None):
        raise RuntimeError("LLM down")
    _patch_llm(monkeypatch, _boom)
    processor = TaskProcessor(db=db, max_concurrent=1)
    with pytest.raises(RuntimeError, match="LLM down"):
        asyncio.run(processor._process_internal(task_id, db.get_task(task_id)))
    assert db.get_task(task_id)["postprocess_status"] == "failed"


def test_postprocess_does_not_block_event_loop(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    def _slow(self, markdown_text, prompt, context_size=None, cancel_event=None):
        time.sleep(0.3)
        return ("# done\n", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})
    _patch_llm(monkeypatch, _slow)
    processor = TaskProcessor(db=db, max_concurrent=1)
    async def _main():
        order = []
        async def ticker():
            await asyncio.sleep(0.05)
            order.append("ticker")
        async def run_proc():
            await processor._process_internal(task_id, db.get_task(task_id))
            order.append("proc")
        await asyncio.gather(run_proc(), ticker())
        return order
    order = asyncio.run(_main())
    assert order == ["ticker", "proc"]


# ========== W1 guard & reconcile ==========


def test_processor_postprocess_guard_blocks_late_write(tmp_path, monkeypatch):
    """W1: terminal task must not be resurrected; orphan file is harmless."""
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, task_dir = _make_pipeline_task(tmp_path, db)
    db.execute(
        "UPDATE tasks SET postprocess_status = ?, status = ? WHERE task_id = ?",
        ("failed", "cancelled", task_id),
    )
    processor = TaskProcessor(db=db, max_concurrent=1)
    task_data = db.get_task(task_id)
    def _ok(self, markdown_text, prompt, context_size=None, cancel_event=None):
        return ("# done", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})
    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _ok)
    processor._run_postprocess(task_id, task_data, Path(task_dir) / "input" / "auto" / "input.md")
    task = db.get_task(task_id)
    # DB state is protected by the guard — postprocess_status must not change
    assert task["postprocess_status"] == "failed"
    # File is written before the guard (file-first); orphan file on cancelled
    # task is harmless and does not create a deliverable contract.
    assert (Path(task_dir) / "input" / "auto" / "final.md").exists()


def test_reconcile_postprocess_skips_when_disabled(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db, enable_postprocess=False)
    processor = TaskProcessor(db=db, max_concurrent=1)
    processor._reconcile_postprocess_on_abort(task_id)
    assert db.get_task(task_id)["postprocess_status"] == "not_enabled"


def test_reconcile_pending_to_skipped(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    processor = TaskProcessor(db=db, max_concurrent=1)
    processor._reconcile_postprocess_on_abort(task_id)
    assert db.get_task(task_id)["postprocess_status"] == "skipped"


def test_reconcile_processing_to_failed(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    db.execute("UPDATE tasks SET postprocess_status = ? WHERE task_id = ?", ("processing", task_id))
    processor = TaskProcessor(db=db, max_concurrent=1)
    processor._reconcile_postprocess_on_abort(task_id)
    assert db.get_task(task_id)["postprocess_status"] == "failed"


def test_reconcile_leaves_terminal_untouched(tmp_path, monkeypatch):
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    db.execute("UPDATE tasks SET postprocess_status = ? WHERE task_id = ?", ("completed", task_id))
    processor = TaskProcessor(db=db, max_concurrent=1)
    processor._reconcile_postprocess_on_abort(task_id)
    assert db.get_task(task_id)["postprocess_status"] == "completed"


# ========== W3/S4 ==========


def test_postprocess_completed_not_downgraded_by_late_exception(tmp_path, monkeypatch):
    """W3: a post-success exception must not downgrade completed->skipped."""
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    def _ok(self, markdown_text, prompt, context_size=None, cancel_event=None):
        return ("# done", {"context_size": 8192, "chunks": 1, "source_length": 1, "strategy": "mock"})
    monkeypatch.setattr(TitleLLMPostprocessor, "process_markdown", _ok)
    from mineru_mcp.task_queue.state_service import TaskStateService
    def _fail_complete(self, task_id):
        raise RuntimeError("db lock")
    monkeypatch.setattr(TaskStateService, "complete", _fail_complete)
    processor = TaskProcessor(db=db, max_concurrent=1)
    with pytest.raises(RuntimeError, match="db lock"):
        asyncio.run(processor._process_internal(task_id, db.get_task(task_id)))
    assert db.get_task(task_id)["postprocess_status"] == "completed"


def test_disabled_task_keeps_not_enabled_status(tmp_path, monkeypatch):
    """S4: disabled tasks keep creation-time not_enabled, no redundant UPDATE."""
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, _ = _make_pipeline_task(tmp_path, db, enable_postprocess=False)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    processor = TaskProcessor(db=db, max_concurrent=1)
    asyncio.run(processor._process_internal(task_id, db.get_task(task_id)))
    task = db.get_task(task_id)
    assert task["status"] == "completed"
    assert task["postprocess_status"] == "not_enabled"


# ========== round05 Item 5: cancel flag stops multi-chunk processing ==========


def test_cancel_flag_stops_multi_chunk_processing(tmp_path, monkeypatch):
    """Item 5: cancel_event set during chunk loop stops further LLM calls."""
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, task_dir = _make_pipeline_task(tmp_path, db)
    # Force multiple chunks: text > context floor (4096), write into the
    # file so the real process_markdown reads it via _run_postprocess.
    long_text = "A" * 5000 + "\n\n" + "B" * 5000
    (Path(task_dir) / "input" / "auto" / "input.md").write_text(long_text, encoding="utf-8")
    task_data = db.get_task(task_id)
    task_data["postprocess_context_size"] = 4096

    calls = []
    cancel_event = threading.Event()

    def _fake_call(client, url, headers, payload):
        calls.append(1)
        if len(calls) == 1:
            cancel_event.set()
        return {"choices": [{"message": {"content": '{"processed_markdown":"ok","continuity_summary":"cont"}'}}]}

    monkeypatch.setattr(
        TitleLLMPostprocessor, "_call_chat_completions",
        lambda self, client, url, headers, payload: _fake_call(client, url, headers, payload),
    )
    monkeypatch.setattr(TitleLLMPostprocessor, "is_configured", lambda self: True)

    processor = TaskProcessor(db=db, max_concurrent=1)
    with pytest.raises(PostprocessCancelledError):
        processor._run_postprocess(
            task_id, task_data,
            Path(task_dir) / "input" / "auto" / "input.md",
            cancel_event=cancel_event,
        )
    # Only the first chunk should have been processed
    assert len(calls) == 1


# ========== round05 Item 6: W6 error ordering ==========


def test_create_task_reports_llm_config_error_before_rule_validation(tmp_path):
    """Both unconfigured LLM and missing rule → LLM error takes priority."""
    config = _unconfigured_config(tmp_path)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    service = TaskService(db=db, file_manager=fm, config=config)
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="A", caller_id="user-a",
    )
    with pytest.raises(ValidationError, match="Postprocess LLM is not configured"):
        service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(), file_name="input.pdf",
            principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-test",
        )


# ========== round06 Item 2: end-to-end cancel → done callback → terminal state ==========


def test_cancel_during_postprocess_ends_in_cancelled_state(tmp_path, monkeypatch):
    """Full chain: process_task → to_thread → PostprocessCancelledError → CancelledError → _on_task_done → state.cancel."""
    db = _setup_processor_env(tmp_path, monkeypatch)
    task_id, task_dir = _make_pipeline_task(tmp_path, db)
    _patch_subprocess(monkeypatch, _FakeProc(returncode=0))
    # Force multi-chunk with large text
    long_text = "X" * 10000
    (Path(task_dir) / "input" / "auto" / "input.md").write_text(long_text, encoding="utf-8")

    calls = []

    def _set_cancel_after_first(self, client, url, headers, payload):
        calls.append(1)
        for flag in list(_set_cancel_after_first._proc._postprocess_cancel_flags.values()):
            flag.set()
        return {"choices": [{"message": {"content": '{"processed_markdown":"ok","continuity_summary":"c"}'}}]}

    monkeypatch.setattr(TitleLLMPostprocessor, "_call_chat_completions", _set_cancel_after_first)
    monkeypatch.setattr(TitleLLMPostprocessor, "is_configured", lambda s: True)

    task_data = db.get_task(task_id)
    task_data["postprocess_context_size"] = 4096

    async def _run():
        proc = TaskProcessor(db=db, max_concurrent=1)
        # The mock references proc._postprocess_cancel_flags
        _set_cancel_after_first._proc = proc
        await proc.process_task(task_id, task_data)
        inner = proc.active_tasks[task_id]
        try:
            await inner
        except asyncio.CancelledError:
            pass  # expected: cancel flag triggers CancelledError

    asyncio.run(_run())
    task = db.get_task(task_id)
    assert task["status"] == "cancelled"
    assert task["postprocess_status"] == "failed"
    assert len(calls) == 1


def test_create_task_reports_llm_config_error_with_valid_rule(tmp_path):
    """Unconfigured LLM but valid rule → LLM error still fires first."""
    config = _unconfigured_config(tmp_path)
    db = TaskDatabase(db_path=str(tmp_path / "tasks.db"))
    fm = FileManager(output_root=str(tmp_path / "output"))
    service = TaskService(db=db, file_manager=fm, config=config)
    db.create_postprocess_rule(
        rule_id="ppr-test", title="test", prompt="clean",
        output_filename="out.md", enabled=True,
    )
    principal = CurrentPrincipal(
        principal_id="user-a", principal_type=PrincipalType.API_KEY,
        role=PrincipalRole.USER, display_name="A", caller_id="user-a",
    )
    with pytest.raises(ValidationError, match="Postprocess LLM is not configured"):
        service.create_task_from_base64(
            file_base64=_minimal_pdf_base64(), file_name="input.pdf",
            principal=principal, enable_postprocess=True, postprocess_rule_id="ppr-test",
        )
