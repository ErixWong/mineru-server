"""Caller 页数配额服务。"""

import json
import math
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from mineru_mcp.errors import quota_exceeded
from mineru_mcp.task_queue import FileManager, TaskDatabase
from mineru_mcp.task_queue.file_manager import resolve_stored_filename


class QuotaService:
    """管理调用方页数预扣、结算、返还与充值。"""

    def __init__(self, db: TaskDatabase):
        self.db = db

    @staticmethod
    def estimate_pages(file_path: Path, start_page_id: int = 0, end_page_id: int = 99999) -> int:
        """估算文件在指定页码范围内将被解析的页数。"""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        start_page_id = max(0, int(start_page_id))
        end_page_id = int(end_page_id)

        if suffix != ".pdf":
            return int(start_page_id <= 0 <= end_page_id)

        try:
            import pypdfium2 as pdfium
        except (ImportError, OSError):
            # 未安装 PDFium 时按每 100 KB 一页向上估算，避免小体积扫描件被低估。
            page_count = max(1, math.ceil(file_path.stat().st_size / 100_000))
        else:
            try:
                document = pdfium.PdfDocument(str(file_path))
                try:
                    page_count = len(document)
                finally:
                    document.close()
            except Exception as exc:
                # 文件损坏或 PDFium 无法读取时同样退化到保守的文件大小估算。
                logger.warning(f"PDF 页数读取失败，改用文件大小估算: {file_path.name}: {exc}")
                page_count = max(1, math.ceil(file_path.stat().st_size / 100_000))

        if end_page_id < start_page_id or start_page_id >= page_count or end_page_id < 0:
            return 0
        return max(0, min(page_count, end_page_id + 1) - start_page_id)

    def reserve(self, caller_id: Optional[str], task_id: str, pages: int) -> Optional[int]:
        """原子预扣；不足时抛出带剩余/需求页数的 403 错误。"""
        if not caller_id:
            return None
        allowed, balance = self.db.reserve_quota_pages(caller_id, task_id, pages)
        if not allowed:
            raise quota_exceeded(int(balance or 0), int(pages))
        return balance

    def settle(
        self,
        caller_id: Optional[str],
        task_id: str,
        actual_pages: Optional[int] = None,
    ) -> Optional[int]:
        """按真实页数结算；缺少产物页数时回退到预扣值。"""
        return self.db.settle_quota_pages(caller_id, task_id, actual_pages)

    def release(self, caller_id: Optional[str], task_id: str) -> bool:
        """失败或取消时幂等返还全部预扣页数。"""
        return self.db.release_quota_pages(caller_id, task_id)

    def top_up(self, caller_id: str, pages: int, reason: str) -> dict[str, Any]:
        """管理员充值入口（本期仅提供服务层能力）。"""
        return self.db.top_up_quota_pages(caller_id, pages, reason)

    @staticmethod
    def actual_pages_from_task(task: Optional[dict[str, Any]]) -> Optional[int]:
        """优先从 middle_json 的 pdf_info 读取页数，缺失时尝试 content_list。"""
        if not task:
            return None
        task_dir = Path(task.get("task_dir") or "")
        task_id = task.get("task_id")
        input_filename = task.get("input_filename")
        if not task_id or not input_filename or not task_dir.is_dir():
            return None

        try:
            stored_name = resolve_stored_filename(task_id, input_filename, task_dir)
            output_files = FileManager(output_root=str(task_dir.parent)).get_output_files(
                task_dir,
                stored_name,
                task.get("backend") or "pipeline",
            )
        except (OSError, ValueError) as exc:
            logger.warning(f"无法定位任务 {task_id} 的页数产物: {exc}")
            return None

        middle_json = output_files.get("middle_json")
        if middle_json and Path(middle_json).is_file():
            middle_json = Path(middle_json)
            try:
                with middle_json.open("r", encoding="utf-8") as file:
                    payload = json.load(file)
                pdf_info = payload.get("pdf_info") if isinstance(payload, dict) else None
                if isinstance(pdf_info, list):
                    return len(pdf_info)
                if isinstance(pdf_info, dict):
                    pages = pdf_info.get("pages")
                    if isinstance(pages, list):
                        return len(pages)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"读取任务 {task_id} middle_json 页数失败: {exc}")

        content_list = output_files.get("content_list")
        if content_list and Path(content_list).is_file():
            content_list = Path(content_list)
            try:
                with content_list.open("r", encoding="utf-8") as file:
                    payload = json.load(file)
                page_indexes: set[int] = set()

                def collect_page_indexes(value: Any) -> None:
                    if isinstance(value, dict):
                        page_index = value.get("page_idx")
                        if isinstance(page_index, int):
                            page_indexes.add(page_index)
                        elif isinstance(page_index, str) and page_index.isdigit():
                            page_indexes.add(int(page_index))
                        for child in value.values():
                            collect_page_indexes(child)
                    elif isinstance(value, list):
                        for child in value:
                            collect_page_indexes(child)

                collect_page_indexes(payload)
                if page_indexes:
                    return len(page_indexes)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"读取任务 {task_id} content_list 页数失败: {exc}")
        return None
