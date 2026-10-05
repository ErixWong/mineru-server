#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
用法：scripts/backup-db.sh [--db <path>] [--out <dir>] [--keep <n>]
                         [--mode auto|host|container] [--container <name>]

选项：
  --db <path>         宿主机上的 SQLite 数据库路径（默认 /docker/mineru-mcp/output/tasks.db）
  --out <dir>         宿主机可见的备份目录（默认 /docker/mineru-mcp/output/backups）
  --keep <n>          保留最新备份份数，必须大于 0（默认 7）
  --mode <mode>       auto 自动探测，或指定 host/container（默认 auto）
  --container <name>  Docker 容器名（默认 mineru-mcp-all-in-one）
  -h, --help          显示此帮助
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

db_path=/docker/mineru-mcp/output/tasks.db
out_dir=${MINERU_BACKUP_DIR:-/docker/mineru-mcp/output/backups}
keep=7
mode=auto
container=mineru-mcp-all-in-one

while (($# > 0)); do
  case "$1" in
    --db|--out|--keep|--mode|--container)
      option=$1
      (($# >= 2)) || die "$option 缺少参数"
      value=$2
      [[ -n "$value" ]] || die "$option 参数不能为空"
      case "$option" in
        --db) db_path=$value ;;
        --out) out_dir=$value ;;
        --keep) keep=$value ;;
        --mode) mode=$value ;;
        --container) container=$value ;;
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
[[ ! "$keep" =~ ^0+$ ]] || die "--keep 必须大于 0"
case "$mode" in
  auto|host|container) ;;
  *) die "--mode 必须是 auto、host 或 container" ;;
esac
[[ "$db_path" != *$'\n'* && "$out_dir" != *$'\n'* ]] || die "--db 和 --out 路径不能包含换行符"
[[ "$container" != *$'\n'* ]] || die "--container 不能包含换行符"
umask 077

if ! db_path=$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$db_path"); then
  die "无法规范化数据库路径"
fi
if ! out_dir=$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$out_dir"); then
  die "无法规范化备份目录路径"
fi

host_probe() {
  python3 - "$1" <<'PY'
import pathlib
import sqlite3
import sys
import urllib.parse

db_path = pathlib.Path(sys.argv[1])
try:
    db_path = db_path.resolve(strict=True)
except FileNotFoundError:
    print(f"源数据库不存在：{db_path}", file=sys.stderr)
    raise SystemExit(2)
except OSError as exc:
    print(f"无法访问源数据库 {db_path}：{exc}", file=sys.stderr)
    raise SystemExit(2)
if not db_path.is_file():
    print(f"源数据库不是普通文件：{db_path}", file=sys.stderr)
    raise SystemExit(2)
try:
    with db_path.open("rb") as source:
        source.read(1)
except OSError as exc:
    print(f"无法访问源数据库 {db_path}：{exc}", file=sys.stderr)
    raise SystemExit(2)

uri = "file:" + urllib.parse.quote(str(db_path), safe="/") + "?mode=ro"
try:
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
except sqlite3.Error as exc:
    print(f"宿主机只读打开源数据库失败：{exc}", file=sys.stderr)
    raise SystemExit(1)
PY
}

actual_mode=$mode
host_probe_error=
if [[ "$mode" == auto || "$mode" == host ]]; then
  if probe_result=$(host_probe "$db_path" 2>&1); then
    actual_mode=host
  else
    probe_status=$?
    host_probe_error=$probe_result
    if [[ "$mode" == host ]]; then
      die "host 模式不可用：$host_probe_error（WAL 库需要在数据库目录创建或写入 -shm）"
    fi
    if ((probe_status == 2)); then
      die "$host_probe_error"
    fi
    actual_mode=container
    printf '宿主机模式不可用，切换到 container 模式：%s\n' "$host_probe_error" >&2
  fi
fi

run_backup_python() {
  cat <<'PY'
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


db_arg, out_arg, keep_arg, display_out_arg, mode_arg = sys.argv[1:]
os.umask(0o077)
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

out_dir = pathlib.Path(out_arg)
phase = "创建备份目录"
try:
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out_dir, 0o755)
    out_dir = out_dir.resolve(strict=True)
except OSError as exc:
    fail(f"{phase}失败：{exc}")
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
    phase = "读取源库关键表行数"
    source_counts = table_counts(source)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    destination_path = out_dir / f"tasks-{timestamp}.db"
    suffix = 1
    while destination_path.exists():
        destination_path = out_dir / f"tasks-{timestamp}-{suffix:02d}.db"
        suffix += 1

    phase = "创建临时备份"
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

    phase = "设置备份文件权限"
    os.chmod(destination_path, 0o644)

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
    display_path = pathlib.Path(display_out_arg) / destination_path.name
    if mode_arg == "host":
        display_path = destination_path
    print(f"备份文件：{display_path}")
    print(f"文件大小：{size} 字节")
    print("关键表行数：" + (
        ", ".join(f"{table}={count}" for table, count in backup_counts.items())
        if backup_counts
        else "无（目标表均不存在）"
    ))
    print(f"保留份数：{retained}")
    print(f"mode={mode_arg}")
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
}

if [[ "$actual_mode" == host ]]; then
  if ! run_backup_python | python3 - "$db_path" "$out_dir" "$keep" "$out_dir" host; then
    die "host 模式备份失败"
  fi
  exit 0
fi

container_hint="生产数据目录为 root 属主；请确认容器 $container 正在运行且当前用户有 Docker（docker 组）权限"
command -v docker >/dev/null 2>&1 || die "找不到 docker；container 模式需要 Docker CLI。$container_hint"
if ! mounts_json=$(docker inspect -f '{{json .Mounts}}' "$container" 2>&1); then
  die "无法检查容器 $container：$mounts_json。$container_hint"
fi
if ! mapped_paths=$(python3 - "$mounts_json" "$db_path" "$out_dir" 2>&1 <<'PY'
import json
import os
import sys


def canonical(path):
    path = os.path.abspath(path)
    missing = []
    while not os.path.lexists(path):
        parent, name = os.path.split(path)
        if parent == path:
            break
        missing.append(name)
        path = parent
    resolved = os.path.realpath(path)
    return os.path.normpath(os.path.join(resolved, *reversed(missing)))


try:
    mounts = json.loads(sys.argv[1])
except json.JSONDecodeError as exc:
    raise SystemExit(f"无法解析 docker inspect 挂载信息：{exc}")
if not isinstance(mounts, list):
    raise SystemExit("容器没有可用于路径映射的挂载信息")

normalized_mounts = []
for mount in mounts:
    source = mount.get("Source")
    destination = mount.get("Destination")
    if isinstance(source, str) and isinstance(destination, str):
        normalized_mounts.append((canonical(source), os.path.normpath(destination)))


def map_path(host_path):
    path = canonical(host_path)
    matches = []
    for source, destination in normalized_mounts:
        try:
            if os.path.commonpath((path, source)) == source:
                matches.append((len(source), source, destination))
        except ValueError:
            continue
    if not matches:
        raise SystemExit(
            f"宿主机路径无法映射到容器：{host_path}；"
            "该路径需位于已挂载进容器的目录下"
        )
    _, source, destination = max(matches)
    relative = os.path.relpath(path, source)
    container_path = destination if relative == "." else os.path.join(destination, relative)
    return os.path.normpath(container_path), path


try:
    db_container, _ = map_path(sys.argv[2])
    out_container, out_host = map_path(sys.argv[3])
except OSError as exc:
    raise SystemExit(f"路径映射失败：{exc}")

print(db_container)
print(out_container)
print(out_host)
PY
); then
  die "$mapped_paths"
fi
mapfile -t mapped_paths_array <<<"$mapped_paths"
if ((${#mapped_paths_array[@]} != 3)); then
  die "无法解析宿主机到容器的路径映射结果"
fi
db_container_path=${mapped_paths_array[0]}
out_container_path=${mapped_paths_array[1]}
out_host_path=${mapped_paths_array[2]}

if ! run_backup_python | docker exec -i "$container" python3 - \
  "$db_container_path" "$out_container_path" "$keep" "$out_host_path" container; then
  die "container 模式备份失败。$container_hint；同时确认容器内有 python3。宿主机探测结果：${host_probe_error:-未执行}"
fi
