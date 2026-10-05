#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
用法：scripts/backup-db.sh [--db <path>] [--out <dir>] [--keep <n>]

选项：
  --db <path>   SQLite 数据库路径（默认 /docker/mineru-mcp/output/tasks.db）
  --out <dir>   备份目录（默认 MINERU_BACKUP_DIR 或 /home/eric/backups/mineru-mcp）
  --keep <n>    保留最新备份份数，必须大于 0（默认 7）
  -h, --help    显示此帮助
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

db_path=/docker/mineru-mcp/output/tasks.db
out_dir=${MINERU_BACKUP_DIR:-/home/eric/backups/mineru-mcp}
keep=7

while (($# > 0)); do
  case "$1" in
    --db|--out|--keep)
      option=$1
      (($# >= 2)) || die "$option 缺少参数"
      value=$2
      [[ -n "$value" ]] || die "$option 参数不能为空"
      case "$option" in
        --db) db_path=$value ;;
        --out) out_dir=$value ;;
        --keep) keep=$value ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数：$1（使用 --help 查看用法）"
      ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "找不到 python3"
[[ "$keep" =~ ^[0-9]+$ ]] || die "--keep 必须是正整数"

umask 077
if ! mkdir -p -- "$out_dir"; then
  die "无法创建备份目录：$out_dir"
fi
if ! out_dir=$(cd -- "$out_dir" && pwd -P); then
  die "无法访问备份目录：$out_dir"
fi
[[ -w "$out_dir" ]] || die "备份目录不可写：$out_dir"

python3 - "$db_path" "$out_dir" "$keep" <<'PY'
import datetime
import os
import pathlib
import sqlite3
import sys
import tempfile
import urllib.parse


KEY_TABLES = ("tasks", "users", "callers", "admin_sessions")


def fail(message):
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(1)


def table_counts(connection):
    counts = {}
    for table in KEY_TABLES:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if exists:
            quoted_table = '"' + table.replace('"', '""') + '"'
            counts[table] = connection.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]
    return counts


db_arg, out_arg, keep_arg = sys.argv[1:]
try:
    keep = int(keep_arg, 10)
except ValueError:
    fail("--keep 必须是正整数")
if keep <= 0:
    fail("--keep 必须大于 0")

db_path = pathlib.Path(db_arg)
try:
    db_path = db_path.resolve(strict=True)
except FileNotFoundError:
    fail(f"源数据库不存在：{db_arg}")
except OSError as exc:
    fail(f"无法访问源数据库 {db_arg}：{exc}")
if not db_path.is_file():
    fail(f"源数据库不是普通文件：{db_path}")
if not os.access(db_path, os.R_OK):
    fail(f"源数据库不可读：{db_path}")

out_dir = pathlib.Path(out_arg)
if not out_dir.is_dir() or not os.access(out_dir, os.W_OK):
    fail(f"备份目录不可写：{out_dir}")

uri = "file:" + urllib.parse.quote(str(db_path), safe="/") + "?mode=ro"
source = None
destination = None
temporary_path = None
phase = "打开源数据库"
try:
    source = sqlite3.connect(uri, uri=True, timeout=30)
    source.execute("PRAGMA query_only = ON")
    source.execute("BEGIN")
    source_counts = table_counts(source)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    destination_path = out_dir / f"tasks-{timestamp}.db"
    suffix = 1
    while destination_path.exists():
        destination_path = out_dir / f"tasks-{timestamp}-{suffix:02d}.db"
        suffix += 1

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".tasks-backup-", suffix=".tmp", dir=out_dir
    )
    os.close(descriptor)
    temporary_path = pathlib.Path(temporary_name)

    phase = "在线备份"
    destination = sqlite3.connect(str(temporary_path), timeout=30)
    source.backup(destination)

    phase = "校验备份完整性"
    integrity = [
        row[0] for row in destination.execute("PRAGMA integrity_check").fetchall()
    ]
    if integrity != ["ok"]:
        fail("备份 integrity_check 未通过：" + "; ".join(integrity))

    phase = "比对关键表行数"
    backup_counts = table_counts(destination)
    if source_counts != backup_counts:
        fail(
            "关键表行数不一致："
            f"源库={source_counts}，备份={backup_counts}"
        )

    destination.close()
    destination = None
    source.close()
    source = None
    os.replace(temporary_path, destination_path)
    temporary_path = None

    phase = "执行保留策略"
    backups = [
        path
        for path in out_dir.glob("tasks-*.db")
        if path.is_file() and not path.is_symlink()
    ]
    backups.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    expired = backups[keep:]
    if expired:
        print("将删除以下过期备份：")
        for path in expired:
            print(f"  {path}")
        for path in expired:
            path.unlink()
    retained = min(len(backups), keep)
    size = destination_path.stat().st_size
    print(f"备份文件：{destination_path.resolve()}")
    print(f"文件大小：{size} 字节")
    print("关键表行数：" + (
        ", ".join(f"{table}={count}" for table, count in backup_counts.items())
        if backup_counts
        else "无（目标表均不存在）"
    ))
    print(f"保留份数：{retained}")
except SystemExit:
    raise
except (sqlite3.Error, OSError, ValueError) as exc:
    fail(f"{phase}失败：{exc}")
finally:
    if destination is not None:
        destination.close()
    if source is not None:
        source.close()
    if temporary_path is not None:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"警告：无法清理临时备份 {temporary_path}：{exc}", file=sys.stderr)
PY
