#!/usr/bin/env python3
"""多用户门户与页数额度的 API 级真机 e2e（直接运行，非 pytest）。

在仓库根目录、已安装项目依赖的 Python 环境运行：
    python tests/manual/quota_portal_e2e.py

脚本使用随机端口、独立临时数据库和 output 目录启动 `mineru-mcp --mode http --no-mcp`，
通过 HTTP 验证用户、充值、任务预扣/超时返还、额度不足及资源隔离；结束后清理服务和临时目录。
"""

from __future__ import annotations

import base64
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF = REPO_ROOT / "tests" / "mineru_test_sample.pdf"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
T = TypeVar("T")


def strong_password() -> str:
    """生成满足最小复杂度校验的随机密码。"""
    return "Aa1!" + secrets.token_urlsafe(24)


def choose_port() -> int:
    """由系统分配一个当前空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_two_page_pdf(destination: Path) -> Path:
    """将仓库的一页 PDF 样本复制为两页，供额度不足场景使用。"""
    from pypdf import PdfReader, PdfWriter

    if not SAMPLE_PDF.is_file():
        raise FileNotFoundError(f"缺少仓库 PDF 样本：{SAMPLE_PDF}")
    reader = PdfReader(str(SAMPLE_PDF))
    if len(reader.pages) != 1:
        raise AssertionError(f"预期仓库样本为 1 页，实际为 {len(reader.pages)} 页")

    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_page(reader.pages[0])
    with destination.open("wb") as output:
        writer.write(output)

    if len(PdfReader(str(destination)).pages) != 2:
        raise AssertionError("临时额度测试 PDF 未生成预期的 2 页")
    return destination


def check_status(response: httpx.Response, expected: int, action: str) -> None:
    if response.status_code != expected:
        raise AssertionError(
            f"{action} 应返回 HTTP {expected}，实际为 {response.status_code}: "
            f"{response.text[:400]}"
        )


class Steps:
    """输出并汇总逐步执行结果。"""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name: str, action: Callable[[], T]) -> T:
        try:
            result = action()
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            self.results.append((name, False, message))
            print(f"[FAIL] {name}: {type(exc).__name__}: {message[:400]}", flush=True)
            raise

        detail = result if isinstance(result, str) else ""
        self.results.append((name, True, detail))
        suffix = f" — {detail}" if detail else ""
        print(f"[PASS] {name}{suffix}", flush=True)
        return result

    def finish(self, name: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            self.results.append((name, False, message))
            print(f"[FAIL] {name}: {type(exc).__name__}: {message[:400]}", flush=True)
        else:
            self.results.append((name, True, ""))
            print(f"[PASS] {name}", flush=True)

    def summary(self) -> bool:
        passed = sum(1 for _, succeeded, _ in self.results if succeeded)
        failed = len(self.results) - passed
        print(f"\n结果：{passed} PASS / {failed} FAIL / {len(self.results)} 步", flush=True)
        for name, succeeded, message in self.results:
            if not succeeded:
                print(f"  FAIL {name}: {message[:400]}", flush=True)
        return failed == 0


class IsolatedServer:
    """管理独立 HTTP 服务子进程及其进程组。"""

    def __init__(self, work_dir: Path, port: int, admin_password: str):
        self.work_dir = work_dir
        self.port = port
        self.admin_password = admin_password
        self.base_url = f"http://127.0.0.1:{port}"
        self.log_path = work_dir / "server.log"
        self.log_file = None
        self.process: subprocess.Popen | None = None

    def start_and_wait(self) -> str:
        output_root = self.work_dir / "output"
        env = os.environ.copy()
        source_path = str(REPO_ROOT / "src")
        inherited_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            source_path + os.pathsep + inherited_pythonpath
            if inherited_pythonpath
            else source_path
        )
        env.update(
            {
                "MINERU_OUTPUT_ROOT": str(output_root),
                "MINERU_DB_PATH": str(output_root / "tasks.db"),
                "MINERU_ADMIN_INITIAL_PASSWORD": self.admin_password,
                "MINERU_CALLER_KEY_MASTER_KEY": base64.urlsafe_b64encode(
                    secrets.token_bytes(32)
                ).decode("ascii"),
                "MINERU_DEFAULT_BACKEND": "pipeline",
                "MINERU_TASK_TIMEOUT": "1",
                "MINERU_RETRY_LIMIT": "0",
                "MINERU_MAX_CONCURRENT": "1",
                "MCP_SERVER_MODE": "http",
                "MCP_HTTP_HOST": "127.0.0.1",
                "MCP_HTTP_PORT": str(self.port),
                "MCP_LOG_LEVEL": "WARNING",
            }
        )

        self.log_file = self.log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mineru_mcp.cli",
                "--mode",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--no-mcp",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"独立服务提前退出，exit code={self.process.returncode}"
                )
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=1)
                if response.status_code == 200:
                    return self.base_url
            except httpx.RequestError:
                pass
            time.sleep(0.25)

        raise TimeoutError("独立服务 60 秒内未通过 /health")

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            except ProcessLookupError:
                process.wait(timeout=10)

        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None


def run_e2e(steps: Steps, server: IsolatedServer) -> None:
    base_url = steps.run("启动独立服务并等待 /health", server.start_and_wait)
    origin = base_url
    admin = httpx.Client(base_url=base_url, timeout=30)
    primary_session: httpx.Client | None = None
    quota_session: httpx.Client | None = None

    try:
        admin_password = server.admin_password

        def login_admin() -> str:
            nonlocal admin_password

            response = admin.post(
                "/api/admin/login",
                json={"username": "admin", "password": admin_password},
                headers={"Origin": origin},
            )
            check_status(response, 200, "管理员登录")
            payload = response.json()
            if payload.get("role") != "admin":
                raise AssertionError("登录账号不是管理员")

            if payload.get("must_change_password"):
                csrf = admin.cookies.get("admin_csrf")
                if not csrf:
                    raise AssertionError("管理员登录未设置 CSRF cookie")
                replacement = strong_password()
                changed = admin.post(
                    "/api/admin/change-password",
                    json={
                        "old_password": admin_password,
                        "new_password": replacement,
                    },
                    headers={"Origin": origin, "X-CSRF-Token": csrf},
                )
                check_status(changed, 200, "管理员首次登录修改密码")
                admin_password = replacement
                response = admin.post(
                    "/api/admin/login",
                    json={"username": "admin", "password": admin_password},
                    headers={"Origin": origin},
                )
                check_status(response, 200, "管理员密码更新后重新登录")
                if response.json().get("must_change_password"):
                    raise AssertionError("管理员密码更新后仍要求再次修改")

            csrf = admin.cookies.get("admin_csrf")
            if not csrf:
                raise AssertionError("管理员登录未设置 CSRF cookie")
            return "管理员 session 已就绪"

        steps.run("管理员登录并完成首次密码轮换", login_admin)

        def admin_headers() -> dict[str, str]:
            csrf = admin.cookies.get("admin_csrf")
            if not csrf:
                raise AssertionError("管理员 session 缺少 CSRF cookie")
            return {"Origin": origin, "X-CSRF-Token": csrf}

        def create_user(label: str) -> dict:
            username = f"e2e-{label}-{secrets.token_hex(4)}"
            password = strong_password()
            response = admin.post(
                "/api/admin/users",
                json={
                    "username": username,
                    "password": password,
                    "display_name": f"E2E {label}",
                },
                headers=admin_headers(),
            )
            check_status(response, 200, "管理员创建用户")
            user = response.json()
            for field in ("user_id", "caller_id", "api_key"):
                if not user.get(field):
                    raise AssertionError(f"用户创建响应缺少 {field}")
            return {**user, "username": username, "password": password}

        primary = steps.run("管理员创建门户用户并取得一次性 API key", lambda: create_user("main"))
        primary_session = httpx.Client(base_url=base_url, timeout=30)

        def login_user(client: httpx.Client, user: dict) -> dict:
            response = client.post(
                "/api/admin/login",
                json={"username": user["username"], "password": user["password"]},
                headers={"Origin": origin},
            )
            check_status(response, 200, "门户用户登录")
            if response.json().get("role") != "user":
                raise AssertionError("门户账号登录角色不是 user")
            return response.json()

        steps.run(
            "确认新用户初始 NULL 余额代表不限量",
            lambda: _assert_initial_unlimited(primary_session, primary, origin),
        )

        def top_up(user: dict, pages: int, reason: str) -> dict:
            response = admin.post(
                f"/api/admin/users/{user['user_id']}/quota",
                json={"pages": pages, "reason": reason},
                headers=admin_headers(),
            )
            check_status(response, 200, "管理员充值页数")
            return response.json()

        def top_up_primary() -> str:
            entry = top_up(primary, 100, "quota portal e2e initial top-up")
            if entry.get("balance_after") != 100:
                raise AssertionError(f"充值后台账余额应为 100，实际为 {entry.get('balance_after')}")
            login_user(primary_session, primary)
            balance = _portal_balance(primary_session)
            if balance != 100:
                raise AssertionError(f"用户门户余额应为 100，实际为 {balance}")
            return "余额=100 页"

        steps.run("管理员充值 100 页并由用户门户确认余额", top_up_primary)

        def submit_api_key_task(user: dict, pdf_path: Path, end_page_id: int) -> str:
            with pdf_path.open("rb") as pdf_file:
                response = httpx.post(
                    f"{base_url}/api/tasks",
                    headers={"Authorization": f"Bearer {user['api_key']}"},
                    data={
                        "backend": "pipeline",
                        "lang": "ch",
                        "start_page_id": "0",
                        "end_page_id": str(end_page_id),
                    },
                    files={
                        "file": (
                            pdf_path.name,
                            pdf_file,
                            "application/pdf",
                        )
                    },
                    timeout=60,
                )
            check_status(response, 200, "用户 API key 提交解析任务")
            task_id = response.json().get("task_id")
            if not task_id:
                raise AssertionError("任务提交响应缺少 task_id")
            return task_id

        if not SAMPLE_PDF.is_file():
            raise FileNotFoundError(f"缺少仓库 PDF 样本：{SAMPLE_PDF}")
        primary_task_id = steps.run(
            "用户 API key 使用 pipeline 提交仓库 PDF 样本",
            lambda: submit_api_key_task(primary, SAMPLE_PDF, 0),
        )

        def check_reservation() -> int:
            response = admin.get(
                f"/api/admin/users/{primary['user_id']}/quota/ledger"
            )
            check_status(response, 200, "管理员读取额度台账")
            entries = response.json().get("items", [])
            reservation = next(
                (
                    item
                    for item in entries
                    if item.get("task_id") == primary_task_id
                    and item.get("reason") == "task_reservation"
                ),
                None,
            )
            if reservation is None or reservation.get("delta") != -1:
                raise AssertionError(
                    "quota_ledger 未出现该任务的 task_reservation -1"
                )
            if reservation.get("balance_after") != 99:
                raise AssertionError("预扣后余额应为 99 页")
            return int(reservation["delta"])

        reservation_delta = steps.run(
            "验证 quota_ledger 记录 task_reservation -1",
            check_reservation,
        )

        def wait_for_refund() -> str:
            deadline = time.monotonic() + 180
            status = ""
            while time.monotonic() < deadline:
                response = httpx.get(
                    f"{base_url}/api/tasks/{primary_task_id}",
                    headers={"Authorization": f"Bearer {primary['api_key']}"},
                    params={"return_md": "false"},
                    timeout=10,
                )
                check_status(response, 200, "查询真实任务状态")
                task = response.json()
                status = task.get("status", "")
                if status in TERMINAL_STATUSES:
                    break
                time.sleep(0.5)
            else:
                raise TimeoutError("任务 180 秒内未进入终态")

            if status not in {"failed", "cancelled"}:
                raise AssertionError(
                    f"任务应走失败/超时返还路径，实际终态为 {status}"
                )
            task_error = str(task.get("error") or task.get("message") or "")
            if status == "cancelled" and "timeout" not in task_error.lower():
                raise AssertionError(f"任务意外取消而非超时：{task_error[:200]}")

            release = None
            release_deadline = time.monotonic() + 15
            while time.monotonic() < release_deadline:
                ledger_response = admin.get(
                    f"/api/admin/users/{primary['user_id']}/quota/ledger"
                )
                check_status(ledger_response, 200, "读取任务返还流水")
                release = next(
                    (
                        item
                        for item in ledger_response.json().get("items", [])
                        if item.get("task_id") == primary_task_id
                        and item.get("reason") == "task_release"
                    ),
                    None,
                )
                if release is not None:
                    break
                time.sleep(0.25)

            expected_release = -reservation_delta
            if release is None or release.get("delta") != expected_release:
                raise AssertionError(
                    f"预期 task_release +{expected_release}，实际为 "
                    f"{release.get('delta') if release else '无流水'}"
                )
            balance = _portal_balance(primary_session)
            if balance != 100:
                raise AssertionError(f"任务终态后余额应返还至 100，实际为 {balance}")

            outcome = "timeout 取消" if status == "cancelled" else "解析失败"
            return f"终态={status}（{outcome}），task_release +{expected_release}，余额=100 页"

        steps.run("等待任务终态并验证额度返还", wait_for_refund)

        quota_user = steps.run(
            "管理员创建低余额测试用户", lambda: create_user("low-quota")
        )
        quota_session = httpx.Client(base_url=base_url, timeout=30)

        def top_up_limited_user() -> str:
            entry = top_up(quota_user, 1, "quota portal e2e insufficient-balance")
            if entry.get("balance_after") != 1:
                raise AssertionError("测试用户充值后余额应为 1 页")
            login_user(quota_session, quota_user)
            balance = _portal_balance(quota_session)
            if balance != 1:
                raise AssertionError(f"用户门户余额应为 1，实际为 {balance}")
            return "余额=1 页"

        steps.run("为不足额用户充值 1 页并确认余额", top_up_limited_user)

        two_page_pdf = steps.run(
            "从仓库样本生成两页额度测试 PDF",
            lambda: make_two_page_pdf(server.work_dir / "two-page-sample.pdf"),
        )

        def assert_quota_rejected() -> str:
            with two_page_pdf.open("rb") as pdf_file:
                response = httpx.post(
                    f"{base_url}/api/tasks",
                    headers={"Authorization": f"Bearer {quota_user['api_key']}"},
                    data={
                        "backend": "pipeline",
                        "lang": "ch",
                        "start_page_id": "0",
                        "end_page_id": "1",
                    },
                    files={
                        "file": (
                            two_page_pdf.name,
                            pdf_file,
                            "application/pdf",
                        )
                    },
                    timeout=60,
                )
            check_status(response, 403, "不足额任务提交")
            error = response.json().get("detail", {})
            if error.get("error") != "QUOTA_EXCEEDED":
                raise AssertionError(f"错误码不是 QUOTA_EXCEEDED：{error}")
            detail = error.get("detail", {})
            if detail.get("remaining_pages") != 1 or detail.get("requested_pages") != 2:
                raise AssertionError(
                    f"错误页数信息不符：remaining={detail.get('remaining_pages')} "
                    f"requested={detail.get('requested_pages')}"
                )
            balance = _portal_balance(quota_session)
            if balance != 1:
                raise AssertionError(f"拒绝后余额应保持 1，实际为 {balance}")
            return "HTTP 403 QUOTA_EXCEEDED，requested=2，余额仍为 1 页"

        steps.run("验证两页任务因余额不足被拒且余额不变", assert_quota_rejected)

        foreign_task_id = steps.run(
            "另一用户 API key 创建隔离验证任务",
            lambda: submit_api_key_task(quota_user, SAMPLE_PDF, 0),
        )

        def check_portal_scope() -> str:
            response = primary_session.get("/api/portal/tasks")
            check_status(response, 200, "读取门户任务列表")
            tasks = response.json().get("tasks", [])
            task_ids = {item.get("task_id") for item in tasks}
            if primary_task_id not in task_ids:
                raise AssertionError("门户任务列表未包含本人已提交任务")

            foreign = primary_session.get(
                f"/api/portal/tasks/{foreign_task_id}"
            )
            check_status(foreign, 404, "读取他人任务")
            return "本人任务在列表内；他人任务返回 404"

        steps.run("验证门户列表可见本人任务且隐藏他人任务", check_portal_scope)

        def deny_admin_api() -> str:
            response = primary_session.get("/api/admin/users")
            check_status(response, 403, "门户用户访问管理员用户 API")
            error = response.json().get("detail", {})
            if error.get("error") != "FORBIDDEN":
                raise AssertionError(f"管理员接口拒绝错误码不符：{error}")
            return "HTTP 403 FORBIDDEN"

        steps.run("验证门户用户不能访问 /api/admin/users", deny_admin_api)
    finally:
        if primary_session is not None:
            primary_session.close()
        if quota_session is not None:
            quota_session.close()
        admin.close()


def _assert_initial_unlimited(
    client: httpx.Client, user: dict, origin: str
) -> str:
    response = client.post(
        "/api/admin/login",
        json={"username": user["username"], "password": user["password"]},
        headers={"Origin": origin},
    )
    check_status(response, 200, "门户用户登录")
    if response.json().get("role") != "user":
        raise AssertionError("门户账号登录角色不是 user")
    balance = _portal_balance(client)
    if balance is not None:
        raise AssertionError(f"新用户初始余额应为 NULL（不限量），实际为 {balance}")
    return "quota_remaining_pages=NULL（不限量）"


def _portal_balance(client: httpx.Client) -> int | None:
    response = client.get("/api/portal/me")
    check_status(response, 200, "读取门户用户余额")
    return response.json().get("quota_remaining_pages")


def main() -> int:
    steps = Steps()
    temporary = tempfile.TemporaryDirectory(prefix="mineru-quota-portal-e2e-")
    work_dir = Path(temporary.name)
    server = IsolatedServer(
        work_dir=work_dir,
        port=choose_port(),
        admin_password=strong_password(),
    )

    try:
        run_e2e(steps, server)
    except Exception as exc:
        if not steps.results or steps.results[-1][1]:
            message = str(exc).strip() or type(exc).__name__
            steps.results.append(("E2E 流程执行", False, message))
            print(
                f"[FAIL] E2E 流程执行: {type(exc).__name__}: {message[:400]}",
                flush=True,
            )
    finally:
        def cleanup() -> None:
            server.stop()
            temporary.cleanup()
            if work_dir.exists():
                raise RuntimeError("独立服务临时目录未能清理")

        steps.finish("清理独立服务与临时目录", cleanup)

    return 0 if steps.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
