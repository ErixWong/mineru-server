# MinerU 与 MCP Server 任务队列方案契合度分析

## 1. 技术架构对比

### 1.1 MinerU 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    MinerU FastAPI Server                     │
├─────────────────────────────────────────────────────────────┤
│  AsyncTaskManager                                           │
│  ├─ tasks: dict[str, AsyncParseTask]  (内存存储)            │
│  ├─ queue: asyncio.Queue[str]         (FIFO 队列)           │
│  ├─ semaphore: asyncio.Semaphore      (并发控制)            │
│  └─ dispatcher_loop                   (分发协程)            │
├─────────────────────────────────────────────────────────────┤
│  端点:                                                       │
│  ├─ POST /tasks         → 异步提交                          │
│  ├─ POST /file_parse    → 同步等待                          │
│  ├─ GET  /tasks/{id}    → 状态查询                          │
│  ├─ GET  /tasks/{id}/result → 结果获取                      │
│  └─ GET  /health        → 健康检查                          │
├─────────────────────────────────────────────────────────────┤
│  核心函数:                                                   │
│  ├─ aio_do_parse()      → 异步解析（可直接调用）            │
│  └─ do_parse()          → 同步解析（可直接调用）            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 MCP Server 建议架构

```
┌─────────────────────────────────────────────────────────────┐
│                       MCP Server                             │
├─────────────────────────────────────────────────────────────┤
│  TaskManager                                                │
│  ├─ db: SQLite                         (持久化存储)         │
│  ├─ semaphore: asyncio.Semaphore      (并发控制)            │
│  ├─ active_tasks: dict[str, Task]     (执行中的任务)        │
│  └─ processor_loop                    (处理协程)            │
├─────────────────────────────────────────────────────────────┤
│  MCP 工具:                                                   │
│  ├─ mineru_parse_submit    → 提交任务                       │
│  ├─ mineru_parse_status    → 查询状态                       │
│  ├─ mineru_parse_result    → 获取结果                       │
│  ├─ mineru_parse_cancel    → 取消任务                       │
│  └─ mineru_parse_list      → 任务列表                       │
├─────────────────────────────────────────────────────────────┤
│  内部调用:                                                   │
│  ├─ aio_do_parse()          → 直接调用 MinerU 核心函数      │
│  └─ 不需要 HTTP 服务         → 节省资源                      │
└─────────────────────────────────────────────────────────────┘
```

## 2. 功能契合度评估

### 2.1 高契合点 ✅

| 功能点 | MinerU 实现 | MCP Server 适用性 | 说明 |
|--------|-------------|-------------------|------|
| 直接函数调用 | `aio_do_parse()` | **非常适合** | 无需 HTTP，直接集成 |
| 异步处理 | asyncio 协程 | **非常适合** | MCP Server 本身是异步 |
| 并发控制 | Semaphore | **可直接复用** | 代码简单有效 |
| 状态模型 | pending/processing/completed/failed | **完全兼容** | 标准任务状态 |
| 文件存储 | task_id 目录结构 | **可复用** | 结构清晰 |
| 自动清理 | 时间过期机制 | **可借鉴** | 减少手动维护 |

### 2.2 需改进点 ⚠️

| 功能点 | MinerU 现状 | MCP Server 需求 | 改进方案 |
|--------|-------------|-----------------|----------|
| 持久化存储 | 内存字典 | SQLite 数据库 | 新增数据库层 |
| 任务取消 | 无机制 | 需要取消功能 | 增加 `asyncio.Task.cancel()` |
| 超时处理 | 仅客户端超时 | 主动取消任务 | 增加任务超时计时器 |
| 日期分层 | 无 | 可能需要 | 新增日期目录或字段 |
| 任务优先级 | FIFO | 可能需要 | 使用优先级队列 |
| 批量查询 | 无 | 需要 | 增加 list 接口 |

### 2.3 不适用点 ❌

| 功能点 | MinerU | MCP Server | 说明 |
|--------|--------|------------|------|
| HTTP API 设计 | FastAPI 端点 | MCP 工具协议 | 协议不兼容，但内部逻辑可复用 |
| 前端界面 | Swagger UI | 无 | MCP Server 不需要 |

## 3. 集成方案设计

### 3.1 推荐：直接调用模式

**优势**:
- 无需启动额外服务
- 资源占用最小
- 响应延迟最低
- 错误处理更直接

```python
# MCP Server 核心实现
import asyncio
import sqlite3
from pathlib import Path
from mineru.cli.common import aio_do_parse, read_fn

class MinerUProcessor:
    def __init__(self, max_concurrent: int = 3, output_root: str = "./output"):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.output_root = Path(output_root)
        self.active_tasks: dict[str, asyncio.Task] = {}
        
    async def process(self, task_id: str, file_path: str, options: dict):
        """核心处理函数，直接调用 aio_do_parse"""
        async with self.semaphore:
            # 1. 准备输入
            pdf_bytes = await asyncio.to_thread(read_fn, Path(file_path))
            pdf_name = Path(file_path).stem
            output_dir = str(self.output_root / task_id)
            
            # 2. 直接调用 MinerU 核心函数
            await aio_do_parse(
                output_dir=output_dir,
                pdf_file_names=[pdf_name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=options.get("lang_list", ["ch"]),
                backend=options.get("backend", "vlm-auto-engine"),
                parse_method=options.get("parse_method", "auto"),
                formula_enable=options.get("formula_enable", True),
                table_enable=options.get("table_enable", True),
                image_analysis=options.get("image_analysis", True),
                start_page_id=options.get("start_page_id", 0),
                end_page_id=options.get("end_page_id", 99999),
            )
            
            # 3. 返回结果路径
            return {
                "output_dir": output_dir,
                "md_path": f"{output_dir}/{pdf_name}/vlm/{pdf_name}.md",
            }
    
    def cancel(self, task_id: str):
        """取消正在执行的任务"""
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
```

### 3.2 MCP 工具定义

```python
# MCP Server 工具实现
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("mineru-mcp")
processor = MinerUProcessor(max_concurrent=3)

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="mineru_parse_submit",
            description="提交 PDF/图片解析任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "lang": {"type": "string", "default": "ch"},
                    "backend": {"type": "string", "default": "vlm-auto-engine"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="mineru_parse_status",
            description="查询任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="mineru_parse_cancel",
            description="取消任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                },
                "required": ["task_id"],
            },
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "mineru_parse_submit":
        task_id = str(uuid.uuid4())
        # 创建数据库记录
        db.create_task(task_id, arguments)
        # 启动处理
        task = asyncio.create_task(
            processor.process(task_id, arguments["file_path"], arguments)
        )
        processor.active_tasks[task_id] = task
        return [TextContent(type="text", text=f"Task submitted: {task_id}")]
    
    elif name == "mineru_parse_cancel":
        processor.cancel(arguments["task_id"])
        db.update_status(arguments["task_id"], "cancelled")
        return [TextContent(type="text", text="Task cancelled")]
```

## 4. 数据库集成设计

### 4.1 SQLite 表结构

```sql
-- 任务主表
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    backend TEXT NOT NULL DEFAULT 'vlm-auto-engine',
    parse_method TEXT DEFAULT 'auto',
    lang TEXT DEFAULT 'ch',
    options TEXT,                    -- JSON 其他选项
    output_dir TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    timeout_seconds INTEGER DEFAULT 3600,
);

-- 状态索引
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at);

-- 任务日志表（可选）
CREATE TABLE task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
);
```

### 4.2 数据库操作封装

```python
import sqlite3
from contextlib import contextmanager

class TaskDB:
    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def create_task(self, task_id: str, args: dict):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (id, file_path, file_name, backend, lang, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (task_id, args["file_path"], Path(args["file_path"]).stem,
                  args.get("backend", "vlm-auto-engine"), args.get("lang", "ch")))
    
    def update_status(self, task_id: str, status: str, **extra):
        with self._conn() as conn:
            fields = {"status": status}
            if status == "processing":
                fields["started_at"] = "datetime('now')"
            elif status in ("completed", "failed"):
                fields["completed_at"] = "datetime('now')"
            if "error" in extra:
                fields["error"] = extra["error"]
            if "output_dir" in extra:
                fields["output_dir"] = extra["output_dir"]
            
            sql = f"UPDATE tasks SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?"
            conn.execute(sql, (*fields.values(), task_id))
    
    def get_task(self, task_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None
    
    def list_tasks(self, status: str = None, limit: int = 100) -> list:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]
```

## 5. 超时与取消机制

### 5.1 MinerU 现状

- **客户端超时**: `wait_for_task_result` 有超时参数，超时后抛异常
- **服务端无取消**: 任务不会被主动取消，继续占用资源
- **风险**: 长时间运行的任务可能阻塞其他任务

### 5.2 MCP Server 改进方案

```python
class TaskProcessor:
    def __init__(self):
        self.active_tasks: dict[str, asyncio.Task] = {}
        self timeouts: dict[str, asyncio.Task] = {}
    
    async def process_with_timeout(self, task_id: str, timeout: int, **kwargs):
        """带超时的处理"""
        # 创建处理任务
        process_task = asyncio.create_task(self.process(task_id, **kwargs))
        self.active_tasks[task_id] = process_task
        
        # 创建超时监控
        timeout_task = asyncio.create_task(self._timeout_monitor(task_id, timeout))
        self.timeouts[task_id] = timeout_task
        
        try:
            result = await process_task
            # 成功完成，取消超时监控
            timeout_task.cancel()
            return result
        except asyncio.CancelledError:
            # 任务被取消（可能是超时或用户取消）
            db.update_status(task_id, "cancelled")
            raise
        except Exception as e:
            timeout_task.cancel()
            db.update_status(task_id, "failed", error=str(e))
            raise
    
    async def _timeout_monitor(self, task_id: str, timeout: int):
        """超时监控协程"""
        await asyncio.sleep(timeout)
        # 超时，取消任务
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            db.update_status(task_id, "failed", error="Timeout")
    
    def cancel_task(self, task_id: str):
        """用户主动取消"""
        task = self.active_tasks.get(task_id)
        timeout = self.timeouts.get(task_id)
        
        if task and not task.done():
            task.cancel()
        if timeout and not timeout.done():
            timeout.cancel()
        
        db.update_status(task_id, "cancelled")
```

## 6. 总结建议

### 6.1 核心集成方案

```
MCP Server 任务队列
├─ 直接调用 aio_do_parse()（不启动 FastAPI）
├─ SQLite 持久化存储
├─ asyncio.Semaphore 并发控制（复用 MinerU）
├─ 主动超时取消机制
├─ 任务状态 API（MCP 工具）
└─ 文件存储：output/{task_id}/{file_name}/
```

### 6.2 代码复用清单

| MinerU 代码 | MCP Server 复用方式 |
|-------------|---------------------|
| `aio_do_parse()` | 直接调用 |
| `read_fn()` | 直接调用 |
| `asyncio.Semaphore` | 复用模式 |
| `AsyncParseTask` 状态 | 复用状态模型 |
| `cleanup_expired_tasks` | 复用清理逻辑 |
| `prepare_env()` | 复用目录创建 |

### 6.3 不复用代码

| MinerU 代码 | 原因 |
|-------------|------|
| FastAPI 端点 | MCP 协议不同 |
| AsyncTaskManager | 内存存储不适合 |
| 任务 HTTP 调度 | MCP 内部调用即可 |

### 6.4 最终评分

| 评估维度 | 得分 | 说明 |
|----------|------|------|
| 直接调用兼容性 | 9/10 | `aio_do_parse` 完美适配 |
| 并发控制复用 | 8/10 | Semaphore 可直接复用 |
| 状态模型兼容 | 9/10 | 完全一致 |
| 持久化需求 | 3/10 | MinerU 无持久化 |
| 超时处理 | 4/10 | MinerU 缺服务端超时 |
| **总体契合度** | **75%** | 高度契合，需补充持久化和超时取消 |