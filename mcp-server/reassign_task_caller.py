"""一次性脚本：将任务重新指派给指定调用方（caller）。

用途：早期管理台创建的任务归属 admin-console（caller_id 为 NULL），任何 caller
API key 都无法通过公开 API/MCP 访问。此脚本将这些任务的归属改到指定 caller 名下
（owner_id/owner_type/caller_id 三字段同步），之后该 caller 的 key 即可查询与下载。

用法（在 mcp-server 目录下）：

    # 将全部未指派任务划归某 caller
    py -3.13 reassign_task_caller.py --caller-id <caller_id> --all-unassigned

    # 只迁移指定任务
    py -3.13 reassign_task_caller.py --caller-id <caller_id> --task-id <task_id> [--task-id ...]

    # 预览不写入
    py -3.13 reassign_task_caller.py --caller-id <caller_id> --all-unassigned --dry-run

数据库路径默认取 MINERU_DB_PATH（未设置时为 output/tasks.db），也可用 --db 覆盖。
"""

import argparse
import sys

from mineru_mcp.task_queue import TaskDatabase


def main() -> int:
    parser = argparse.ArgumentParser(description="Reassign tasks to a caller")
    parser.add_argument("--caller-id", required=True, help="目标调用方 caller_id")
    parser.add_argument("--task-id", action="append", default=[], help="指定任务 ID（可多次传入）")
    parser.add_argument("--all-unassigned", action="store_true", help="迁移全部 caller_id 为 NULL 的任务")
    parser.add_argument("--db", default=None, help="数据库路径（默认取 MINERU_DB_PATH 或 output/tasks.db）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将迁移的任务，不写入")
    args = parser.parse_args()

    if not args.task_id and not args.all_unassigned:
        parser.error("请指定 --task-id 或 --all-unassigned")

    import os
    db_path = args.db or os.getenv("MINERU_DB_PATH", "output/tasks.db")
    db = TaskDatabase(db_path=db_path)

    caller = db.get_caller(args.caller_id)
    if not caller:
        print(f"[ERROR] caller 不存在: {args.caller_id}")
        return 1
    if int(caller.get("disabled", 0)):
        print(f"[WARN] caller 已禁用: {caller.get('name')}，仍将执行迁移")

    if args.all_unassigned:
        tasks = db.fetch_all("SELECT task_id, input_filename, status FROM tasks WHERE caller_id IS NULL ORDER BY created_at")
    else:
        tasks = []
        for task_id in args.task_id:
            task = db.get_task(task_id)
            if not task:
                print(f"[SKIP] 任务不存在: {task_id}")
                continue
            tasks.append(task)

    if not tasks:
        print("没有需要迁移的任务")
        return 0

    print(f"目标 caller: {caller.get('name')} ({args.caller_id})")
    print(f"待迁移任务: {len(tasks)} 个")
    for task in tasks:
        print(f"  - {task['task_id']}  {task.get('input_filename')}  [{task.get('status')}]")

    if args.dry_run:
        print("dry-run，未写入")
        return 0

    migrated = 0
    for task in tasks:
        updated = db.execute(
            "UPDATE tasks SET caller_id = ?, owner_id = ?, owner_type = 'api_key' WHERE task_id = ?",
            (args.caller_id, args.caller_id, task["task_id"]),
        )
        migrated += int(updated > 0)

    print(f"已迁移 {migrated}/{len(tasks)} 个任务到 caller={args.caller_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
