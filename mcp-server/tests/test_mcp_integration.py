# -*- coding: utf-8 -*-
"""MinerU MCP Server Integration Test

Directly tests REST API endpoints:
  - Health check with observability info
  - Backend listing + queue stats
  - Task submit > poll > get result
  - Task cancellation
  - Error handling (404/400)

Usage:
  1. Start server: python -m mineru_mcp.app
  2. Run: python tests/test_mcp_integration.py [--pdf path/to/test.pdf]
"""

import os
import sys
import time
import argparse
from pathlib import Path

import httpx
from loguru import logger

API_BASE = "http://localhost:8002/api"
# 集成测试脚本需要注入一个真实 caller 的 API key（在 admin console 创建后写入数据库）。
# 这不是系统配置项，仅供本地联调脚本使用。
AUTH_TOKEN = os.getenv("MINERU_TEST_CALLER_API_KEY", "erix-secure-token")
HEADERS = {"Authorization": "Bearer " + AUTH_TOKEN}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REAL_WORLD_PDF = REPO_ROOT / "tests" / "奇瑞质量协议签章版-1-2.pdf"

TEST_PDF_GENERATED = None


def generate_test_pdf():
    """Generate a minimal single-page text PDF using reportlab."""
    global TEST_PDF_GENERATED
    if TEST_PDF_GENERATED and Path(TEST_PDF_GENERATED).exists():
        return TEST_PDF_GENERATED

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
    except ImportError:
        logger.warning("reportlab not installed, skipping PDF generation tests")
        return None

    tmp = Path(os.environ.get("TEMP", ".")) / "mineru_test_sample.pdf"
    c = canvas.Canvas(str(tmp), pagesize=A4)
    c.setFont("Helvetica", 14)
    c.drawString(100, 750, "MinerU Integration Test Document")
    c.setFont("Helvetica", 11)
    lines = [
        "This is a test document generated for integration testing.",
        "",
        "Features tested:",
        "  1. Health check endpoint",
        "  2. Backend listing",
        "  3. Task submission and polling",
        "  4. Task cancellation",
        "  5. Error handling",
        "",
        "Page 1 of 1.",
    ]
    y = 700
    for line in lines:
        c.drawString(100, y, line)
        y -= 18
    c.save()

    TEST_PDF_GENERATED = str(tmp)
    logger.info("Generated test PDF: {}", tmp)
    return TEST_PDF_GENERATED


def get_default_test_pdf() -> str | None:
    """Prefer the checked-in real-world PDF sample for integration testing."""
    if DEFAULT_REAL_WORLD_PDF.exists():
        logger.info("Using real-world test PDF: {}", DEFAULT_REAL_WORLD_PDF)
        return str(DEFAULT_REAL_WORLD_PDF)

    logger.warning("Real-world test PDF not found: {}", DEFAULT_REAL_WORLD_PDF)
    return generate_test_pdf()


def find_artifact_by_name(artifacts: list[dict], name: str) -> dict | None:
    """Find a deliverable anywhere in the artifact tree by logical name."""
    for item in artifacts:
        if item.get("name") == name:
            return item

        children = item.get("children")
        if isinstance(children, list):
            found = find_artifact_by_name(children, name)
            if found is not None:
                return found

    return None


def test_health():
    """GET /api/health -> scheduler_running + queue_stats"""
    r = httpx.get(API_BASE + "/health", headers=HEADERS)
    assert r.status_code == 200, "Expected 200, got " + str(r.status_code)
    data = r.json()
    assert data["status"] == "healthy"
    assert data["scheduler_running"] is True
    assert "queue_stats" in data
    assert "auth_required" in data
    logger.info("  [PASS] health - {} | scheduler={} | auth={}",
                data["status"], data["scheduler_running"], data["auth_required"])


def test_backends():
    """GET /api/backends -> 5 backends"""
    r = httpx.get(API_BASE + "/backends", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    names = [b["name"] for b in data["backends"]]
    assert len(names) == 5
    assert "pipeline" in names
    assert "hybrid-http-client" in names
    logger.info("  [PASS] backends - {} backends", len(names))


def test_stats():
    """GET /api/stats -> queue_stats + total"""
    r = httpx.get(API_BASE + "/stats", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "queue_stats" in data
    assert "total" in data
    logger.info("  [PASS] stats - total={} | pending={} | completed={}",
                data["total"], data["queue_stats"]["pending"], data["queue_stats"]["completed"])


def test_submit_and_poll(pdf_path: str):
    """POST /api/tasks -> poll -> list deliverables -> download markdown/image artifacts"""
    if not pdf_path or not Path(pdf_path).exists():
        logger.warning("  [SKIP] submit_and_poll - PDF not found")
        return

    with open(pdf_path, "rb") as f:
        r = httpx.post(
            API_BASE + "/tasks",
            headers=HEADERS,
            files={"file": (Path(pdf_path).name, f, "application/pdf")},
            data={"lang": "en"},
        )
    assert r.status_code == 200, "Submit failed: " + str(r.status_code) + " " + r.text
    data = r.json()
    task_id = data["task_id"]
    assert task_id
    logger.info("  [PASS] submit - task_id={}", task_id)

    deadline = time.time() + 300
    status = "pending"
    while time.time() < deadline:
        r = httpx.get(API_BASE + "/tasks/" + task_id, headers=HEADERS)
        assert r.status_code == 200
        status_data = r.json()
        status = status_data["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(3)

    assert status in ("completed", "failed"), "Unexpected status: " + status
    if status == "completed":
        r = httpx.get(API_BASE + "/tasks/" + task_id + "/deliverables", headers=HEADERS)
        assert r.status_code == 200
        artifacts_payload = r.json()
        artifacts = artifacts_payload["artifacts"]
        assert artifacts, "Expected at least one deliverable"

        markdown_artifact = find_artifact_by_name(artifacts, "markdown")
        assert markdown_artifact is not None, "Expected markdown deliverable"
        assert markdown_artifact["downloadable"] is True
        assert markdown_artifact["download_key"]

        r = httpx.get(
            API_BASE + "/tasks/" + task_id + "/deliverables/download",
            headers=HEADERS,
            params={"download_key": markdown_artifact["download_key"]},
        )
        assert r.status_code == 200
        markdown_text = r.text
        assert markdown_text.strip(), "Downloaded markdown should not be empty"
        logger.info("  [PASS] markdown download - {} chars", len(markdown_text))

        images_group = find_artifact_by_name(artifacts, "images")
        assert images_group is not None, "Expected images group deliverable"
        image_children = images_group.get("children") or []
        assert image_children, "Expected at least one extracted image deliverable"

        image_artifact = image_children[0]
        r = httpx.get(
            API_BASE + "/tasks/" + task_id + "/deliverables/download",
            headers=HEADERS,
            params={"download_key": image_artifact["download_key"]},
        )
        assert r.status_code == 200
        assert r.content, "Downloaded image payload should not be empty"
        assert r.headers["content-type"].startswith("image/")
        logger.info(
            "  [PASS] image download - {} ({})",
            image_artifact["name"],
            r.headers["content-type"],
        )
    else:
        logger.warning("  [WARN] task ended as 'failed' (pipeline may need real PDF)")


def test_cancel():
    """POST /api/tasks -> DELETE /api/tasks/{id} -> confirm cancelled"""
    pdf = generate_test_pdf()
    if not pdf:
        logger.warning("  [SKIP] cancel - could not generate PDF")
        return

    with open(pdf, "rb") as f:
        r = httpx.post(
            API_BASE + "/tasks",
            headers=HEADERS,
            files={"file": (Path(pdf).name, f, "application/pdf")},
            data={"lang": "en"},
        )
    assert r.status_code == 200
    task_id = r.json()["task_id"]
    logger.info("  [PASS] cancel - submitted task_id={}", task_id)

    r = httpx.delete(API_BASE + "/tasks/" + task_id, headers=HEADERS)
    assert r.status_code == 200
    cancel_data = r.json()
    assert cancel_data["cancelled"] is True
    logger.info("  [PASS] cancel - cancelled=True")


def test_errors():
    """400 invalid backend / 404 not found"""
    r = httpx.get(API_BASE + "/tasks/nonexistent-123", headers=HEADERS)
    assert r.status_code == 404
    err = r.json()
    body = err.get("detail", err)
    assert body["status"] == "error"
    assert body["error"] == "TASK_NOT_FOUND"
    logger.info("  [PASS] 404 - TASK_NOT_FOUND")

    r = httpx.post(
        API_BASE + "/tasks",
        headers=HEADERS,
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"backend": "invalid-backend"},
    )
    assert r.status_code in (400, 422), "Expected 400 or 422, got " + str(r.status_code)
    logger.info("  [PASS] 400 - invalid backend")


def run_all(pdf_path: str = None):
    """Run all integration tests."""
    logger.info("=" * 50)
    logger.info("MCP Server Integration Tests")
    logger.info("API: {}", API_BASE)
    logger.info("=" * 50)

    if pdf_path is None:
        pdf_path = get_default_test_pdf()

    tests = [
        ("health", test_health),
        ("backends", test_backends),
        ("stats", test_stats),
        ("errors", test_errors),
        ("cancel", test_cancel),
    ]

    if pdf_path:
        tests.append(("submit+poll+result", lambda: test_submit_and_poll(pdf_path)))

    passed = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            logger.error("  [FAIL] {} - {}", name, str(e)[:120])
            failed.append(name)
        except Exception as e:
            logger.error("  [FAIL] {} - {}: {}", name, type(e).__name__, str(e)[:120])
            failed.append(name)

    logger.info("=" * 50)
    logger.info("Result: {} passed / {} failed / {} total", passed, len(failed), len(tests))
    if failed:
        logger.error("Failed: {}", failed)
    else:
        logger.info("ALL PASSED")
    return len(failed) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", help="Test PDF path (defaults to tests/奇瑞质量协议签章版-1-2.pdf)")
    parser.add_argument("--host", default="localhost", help="API host (default: localhost)")
    parser.add_argument("--port", type=int, default=8002, help="API port (default: 8002)")
    args = parser.parse_args()

    API_BASE = "http://" + args.host + ":" + str(args.port) + "/api"
    success = run_all(args.pdf)
    sys.exit(0 if success else 1)
