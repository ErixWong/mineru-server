"""Postprocess run executor.

后处理执行器：以 run（执行实例）为单位调度后处理流水线。

设计要点：
- 与解析并发完全分离：独立信号量（MINERU_POSTPROCESS_MAX_CONCURRENT），
  LLM 调用是 IO 密集，不与 GPU 解析抢占槽位。
- 步骤串联传递：第 N 步的输入是第 N-1 步的输出文件。
- 产物覆盖写：同一 output_filename 重跑时幂等覆盖。
- 重启恢复：running 的 run 回退 pending 重新认领（覆盖写保证幂等）。
"""

import asyncio
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from mineru_mcp.config import MCPConfig, get_config
from mineru_mcp.postprocess import (
    PostprocessCancelledError,
    TitleLLMPostprocessor,
    build_postprocess_output_path,
    normalize_output_filename,
)

from .database import TaskDatabase
from .file_manager import FileManager, resolve_stored_filename


def resolve_steps_snapshot(
    db: TaskDatabase,
    steps: List[Dict[str, Any]],
    plan_label: str = "Plan",
    default_context_size: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """将步骤数组解析为可执行的步骤快照（plan 保存前校验与 run 冻结共用）。

    每步展开为自包含结构（不依赖 action/plan 表后续变更）：
    {action_id, name, type, prompt, context_size, output_filename}

    Raises:
        ValueError: 步骤为空，或引用的 action 不存在/停用/类型不支持。
    """
    if not steps:
        raise ValueError(f"{plan_label} has no steps")

    snapshot: List[Dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        action_id = step.get("action_id")
        action = db.get_postprocess_action(action_id) if action_id else None
        if not action:
            raise ValueError(f"{plan_label} step {index}: action '{action_id}' not found")
        if not int(action.get("enabled", 0)):
            raise ValueError(f"{plan_label} step {index}: action '{action_id}' is disabled")
        if action.get("type") != "llm_transform":
            raise ValueError(f"{plan_label} step {index}: unsupported action type '{action.get('type')}'")

        config = action.get("config") or {}
        output_filename = normalize_output_filename(
            step.get("output_filename") or config.get("output_filename")
        )
        context_size = config.get("context_size") or default_context_size
        snapshot.append({
            "action_id": action["action_id"],
            "name": action["name"],
            "type": action["type"],
            "prompt": config.get("prompt") or "",
            "context_size": context_size,
            "output_filename": output_filename,
        })
    return snapshot


def build_plan_steps_snapshot(
    db: TaskDatabase,
    plan_id: str,
    default_context_size: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """将 plan 解析为可执行的步骤快照。

    Args:
        db: TaskDatabase instance.
        plan_id: Plan ID.
        default_context_size: 步骤未自带 context_size 时的默认值
            （如创建任务时传入的 postprocess_context_size）。

    Raises:
        ValueError: plan 不存在/停用/无步骤，或引用的 action 不存在/停用。
    """
    plan = db.get_postprocess_plan(plan_id)
    if not plan:
        raise ValueError(f"Postprocess plan '{plan_id}' not found")
    if not int(plan.get("enabled", 0)):
        raise ValueError(f"Postprocess plan '{plan_id}' is disabled")

    return resolve_steps_snapshot(
        db,
        plan.get("steps") or [],
        plan_label=f"Plan '{plan_id}'",
        default_context_size=default_context_size,
    )


class PostprocessRunner:
    """后处理 run 调度与执行器（单进程内运行，随应用生命周期启停）。"""

    def __init__(
        self,
        db: TaskDatabase,
        max_concurrent: int = 2,
        poll_interval: float = 1.0,
        config: Optional[MCPConfig] = None,
    ):
        self.db = db
        self.config = config or get_config()
        self.max_concurrent = max(1, max_concurrent)
        self.poll_interval = poll_interval
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active: Dict[str, asyncio.Task] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._running = False
        self._fetch_paused = False
        self._poll_task: Optional[asyncio.Task] = None
        logger.info(f"PostprocessRunner initialized with max_concurrent={self.max_concurrent}")

    # ==================== Run 创建（自动/手动共用） ====================

    def create_run(
        self,
        task_id: str,
        plan_id: str,
        trigger_source: str = "manual",
        default_context_size: Optional[int] = None,
    ) -> str:
        """为任务创建一个后处理 run（快照在创建时冻结）。

        Returns:
            run_id。

        Raises:
            ValueError: 任务不存在或 plan 无法解析。
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        plan = self.db.get_postprocess_plan(plan_id)
        steps_snapshot = build_plan_steps_snapshot(self.db, plan_id, default_context_size)

        run_id = f"pprun-{uuid.uuid4().hex[:12]}"
        self.db.create_postprocess_run(
            run_id=run_id,
            task_id=task_id,
            plan_id=plan_id,
            plan_title_snapshot=(plan or {}).get("title") or plan_id,
            steps_snapshot=steps_snapshot,
            trigger_source=trigger_source,
        )
        logger.info(f"Postprocess run {run_id} created for task {task_id} (plan={plan_id}, source={trigger_source})")
        return run_id

    # ==================== 生命周期 ====================

    async def start(self) -> None:
        """启动 runner：恢复中断的 run 并开启轮询。"""
        if self._running:
            return
        recovered = self.db.reset_running_postprocess_runs()
        if recovered:
            logger.info(f"Recovered {recovered} interrupted postprocess runs on startup")
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("PostprocessRunner started")

    async def stop(self) -> None:
        """停止 runner：取消轮询并请求所有活跃 run 取消。"""
        if not self._running:
            return
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        for run_id, flag in list(self._cancel_flags.items()):
            flag.set()
        for run_id, task in list(self._active.items()):
            task.cancel()
        logger.info("PostprocessRunner stopped")

    def get_active_count(self) -> int:
        return len([t for t in self._active.values() if not t.done()])

    def pause_fetching(self) -> None:
        """Pause claiming new pending postprocess runs."""
        self._fetch_paused = True
        logger.info("PostprocessRunner pending-run fetching paused")

    def resume_fetching(self) -> None:
        """Resume claiming new pending postprocess runs."""
        self._fetch_paused = False
        logger.info("PostprocessRunner pending-run fetching resumed")

    # ==================== 取消 ====================

    def cancel_run(self, run_id: str) -> bool:
        """取消 run：pending 直接 CAS 取消；running 置取消标志（分片边界生效）。"""
        run = self.db.get_postprocess_run(run_id)
        if not run:
            return False
        status = run.get("status")
        if status == "pending":
            return self.db.cancel_pending_postprocess_run(run_id)
        if status == "running":
            flag = self._cancel_flags.get(run_id)
            if flag is not None:
                flag.set()
                logger.info(f"Postprocess run {run_id} cancel requested")
                return True
        return False

    # ==================== 调度 ====================

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                if self._fetch_paused:
                    continue
                available = self.max_concurrent - self.get_active_count()
                if available <= 0:
                    continue
                pending_runs = self.db.list_postprocess_runs(status="pending", limit=available)
                for run in pending_runs:
                    run_id = run["run_id"]
                    if run_id in self._active:
                        continue
                    if self.db.claim_postprocess_run(run_id):
                        task = asyncio.create_task(self._execute_run(run_id))
                        self._active[run_id] = task
                        task.add_done_callback(lambda t, rid=run_id: self._on_run_done(rid, t))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"PostprocessRunner poll loop error: {e}")
                await asyncio.sleep(5)

    def _on_run_done(self, run_id: str, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning(f"Postprocess run {run_id} asyncio task cancelled")
        except Exception as e:
            logger.error(f"Postprocess run {run_id} execution error: {e}")
        finally:
            self._active.pop(run_id, None)
            self._cancel_flags.pop(run_id, None)

    # ==================== 执行 ====================

    async def _execute_run(self, run_id: str) -> None:
        cancel_event = threading.Event()
        self._cancel_flags[run_id] = cancel_event
        try:
            async with self.semaphore:
                await self._execute_run_inner(run_id, cancel_event)
        finally:
            self._cancel_flags.pop(run_id, None)

    async def _execute_run_inner(self, run_id: str, cancel_event: threading.Event) -> None:
        run = self.db.get_postprocess_run(run_id)
        if not run:
            logger.warning(f"Postprocess run {run_id} disappeared before execution")
            return
        task = self.db.get_task(run["task_id"])
        if not task:
            self.db.finish_postprocess_run(run_id, "failed", error="Task not found")
            return

        task_id = task["task_id"]
        task_dir = Path(task["task_dir"])
        stored_name = resolve_stored_filename(task_id, task["input_filename"], task_dir)
        file_manager = FileManager(output_root=str(self.db.db_path.parent))
        md_path = file_manager.get_output_files(task_dir, stored_name, task["backend"])["md"]

        if not md_path.exists():
            self.db.finish_postprocess_run(run_id, "failed", error=f"Source markdown not found: {md_path.name}")
            return

        steps = run.get("steps_snapshot") or []
        step_results: List[Dict[str, Any]] = [
            {
                "action_id": step.get("action_id"),
                "name": step.get("name"),
                "status": "pending",
                "output_filename": step.get("output_filename"),
                "chunks": 0,
                "error": None,
            }
            for step in steps
        ]

        input_path = md_path
        try:
            for index, step in enumerate(steps):
                if cancel_event.is_set():
                    raise PostprocessCancelledError(f"Run cancelled before step {index + 1}/{len(steps)}")

                step_results[index]["status"] = "running"
                self.db.update_postprocess_run_steps(run_id, index, step_results)

                markdown_text = input_path.read_text(encoding="utf-8")
                postprocessor = TitleLLMPostprocessor(self.config)
                processed_text, metadata = await asyncio.to_thread(
                    postprocessor.process_markdown,
                    markdown_text,
                    step.get("prompt") or "",
                    step.get("context_size"),
                    cancel_event,
                )

                # 串联传递：本步输出即下一步输入；同名覆盖写保证重跑幂等。
                output_path = build_postprocess_output_path(md_path, step["output_filename"])
                output_path.write_text(
                    processed_text + ("\n" if processed_text and not processed_text.endswith("\n") else ""),
                    encoding="utf-8",
                )

                step_results[index]["status"] = "completed"
                step_results[index]["chunks"] = metadata.get("chunks", 1)
                self.db.update_postprocess_run_steps(run_id, index, step_results)
                input_path = output_path

            finished = self.db.finish_postprocess_run(run_id, "completed")
            if finished:
                self.db.add_log(
                    task_id, "INFO",
                    f"Postprocess run {run_id} completed: plan={run.get('plan_title_snapshot')} steps={len(steps)}",
                )
                logger.info(f"Postprocess run {run_id} completed for task {task_id}")

        except PostprocessCancelledError as e:
            for result in step_results:
                if result["status"] == "running":
                    result["status"] = "cancelled"
            self._mark_unfinished_steps(step_results, "skipped")
            self.db.update_postprocess_run_steps(run_id, len(steps), step_results)
            self.db.finish_postprocess_run(run_id, "cancelled")
            self.db.add_log(task_id, "INFO", f"Postprocess run {run_id} cancelled: {e}")
            logger.info(f"Postprocess run {run_id} cancelled")

        except Exception as e:
            error_msg = str(e)[:500]
            for result in step_results:
                if result["status"] == "running":
                    result["status"] = "failed"
                    result["error"] = error_msg
            self._mark_unfinished_steps(step_results, "skipped")
            self.db.update_postprocess_run_steps(run_id, len(steps), step_results)
            self.db.finish_postprocess_run(run_id, "failed", error=error_msg)
            self.db.add_log(task_id, "ERROR", f"Postprocess run {run_id} failed: {error_msg}")
            logger.error(f"Postprocess run {run_id} failed: {error_msg}")

    @staticmethod
    def _mark_unfinished_steps(step_results: List[Dict[str, Any]], status: str) -> None:
        for result in step_results:
            if result["status"] == "pending":
                result["status"] = status
