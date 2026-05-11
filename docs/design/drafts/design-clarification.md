# 任务队列方案设计澄清与简化

## 1. MinerU 输出路径：为什么是 `{pdf_name}/vlm/`？

### 1.1 这是 MinerU 的默认行为

**MinerU `aio_do_parse()` 函数调用后，输出路径由 MinerU 决定**：

```python
# MinerU 源码 common.py:175-180
def prepare_env(output_dir, pdf_file_name, parse_method):
    local_md_dir = str(os.path.join(output_dir, pdf_file_name, parse_method))
    local_image_dir = os.path.join(str(local_md_dir), "images")
    os.makedirs(local_image_dir, exist_ok=True)
    os.makedirs(local_md_dir, exist_ok=True)
    return local_image_dir, local_md_dir
```

**实际输出路径**：
- `output_dir` = `output/2026/05/10/{uuid}/`
- `pdf_file_name` = `"document"`（从 input.pdf 提取）
- `parse_method` = `"vlm"`（backend 类型）
- 最终路径：`output/2026/05/10/{uuid}/document/vlm/`

**这是 MinerU 的设计，我们无法改变**（除非修改 MinerU 源码）。

### 1.2 是否需要遵循？

**方案 A：遵循 MinerU 默认行为（推荐）**
- ✅ 不修改 MinerU 源码
- ✅ 保持 MinerU 可 git pull 更新
- ⚠️ 目录结构稍复杂

**方案 B：修改 MinerU 源码**
- ❌ 破坏 MinerU 更新能力
- ❌ 维护成本高
- ✅ 目录结构简单

**建议：遵循 MinerU 默认行为（方案 A）**

---

## 2. 并发控制逻辑：简化方案

### 2.1 用户建议的方案（简单有效）

```
后台 clock（定时轮询，如每秒）
    ↓
检查：当前处理中任务数 < max_concurrent ?
    ↓
是 → 从数据库领取一个 pending 任务
    ↓
否 → 跳过，等待下次轮询
```

### 2.2 实现代码

```python
class TaskScheduler:
    def __init__(self, processor: TaskProcessor, config: Config):
        self.processor = processor
        self.config = config
        self.db = Database(config.db_path)
        
    async def start(self):
        """启动定时轮询"""
        asyncio.create_task(self._poll_loop())
        
    async def _poll_loop(self):
        """定时轮询（clock）"""
        while True:
            await asyncio.sleep(1)  # 每秒轮询
            
            # 检查当前处理中任务数
            active_count = len(self.processor.active_tasks)
            
            if active_count < self.config.max_concurrent:
                # 领取一个 pending 任务
                task = self.db.fetch_one("""
                    SELECT * FROM tasks 
                    WHERE status = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT 1
                """)
                
                if task:
                    # 更新状态为 processing
                    self.db.update(
                        "UPDATE tasks SET status = 'processing', started_at = NOW() WHERE task_id = ?",
                        (task['task_id'],)
                    )
                    # 启动处理
                    asyncio.create_task(
                        self.processor.process_task(task['task_id'], task)
                    )
```

**优势**：
- ✅ 简单直观，易于理解
- ✅ 不需要复杂的乐观锁
- ✅ 内存中检查活跃任务数，避免数据库压力

**关键点**：
- `active_tasks` 需要在任务完成/失败/取消时及时清理

---

## 3. 超时机制：在 clock 里检查

### 3.1 用户建议的方案

```
后台 clock（定时轮询）
    ↓
检查：processing 任务中，started_at + timeout_seconds < NOW() ?
    ↓
是 → 找到对应的 asyncio.Task，调用 task.cancel()
    ↓
更新数据库状态为 failed
```

### 3.2 实现代码

```python
class TaskScheduler:
    async def _poll_loop(self):
        """定时轮询（clock）：领取任务 + 检查超时"""
        while True:
            await asyncio.sleep(1)
            
            # 1. 领取任务
            await self._fetch_pending_tasks()
            
            # 2. 检查超时
            await self._check_timeout_tasks()
            
    async def _fetch_pending_tasks(self):
        """领取待处理任务"""
        active_count = len(self.processor.active_tasks)
        
        if active_count < self.config.max_concurrent:
            task = self.db.fetch_one("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1")
            
            if task:
                self.db.update("UPDATE tasks SET status = 'processing', started_at = NOW() WHERE task_id = ?", (task['task_id'],))
                asyncio.create_task(self.processor.process_task(task['task_id'], task))
    
    async def _check_timeout_tasks(self):
        """检查超时任务"""
        # 查询数据库中的超时任务
        timeout_tasks = self.db.fetch_all("""
            SELECT task_id, timeout_seconds 
            FROM tasks 
            WHERE status = 'processing' 
            AND started_at IS NOT NULL
            AND NOW() > started_at + timeout_seconds
        """)
        
        for task in timeout_tasks:
            task_id = task['task_id']
            
            # 找到对应的 asyncio.Task 并取消
            active_task = self.processor.active_tasks.get(task_id)
            if active_task and not active_task.done():
                active_task.cancel()
            
            # 更新数据库
            self.db.update("UPDATE tasks SET status = 'failed', error = 'Timeout' WHERE task_id = ?", (task_id,))
            
            # 清理 active_tasks
            self.processor.active_tasks.pop(task_id, None)
```

**优势**：
- ✅ 单一机制，逻辑集中
- ✅ 超时检查和任务领取都在同一个 clock
- ✅ 不需要 `asyncio.wait_for` 的复杂机制

---

## 4. 现有架构整合：展开说明

### 4.1 现有架构分析

**当前 MCP Server 模块**：

| 文件 | 当前功能 | 方案影响 |
|------|---------|---------|
| `mineru_client.py` | MinerU HTTP 客户端 | **完全替换** → 不再通过 HTTP 调用 MinerU |
| `server.py` | MCP 工具定义 | **部分重构** → 修改工具实现，保留接口 |
| `api.py` | REST API | **部分重构** → 修改端点实现，保留接口 |
| `concurrency.py` | 并发控制 | **可复用** → Semaphore 模式可复用 |
| `config.py` | 配置管理 | **扩展** → 新增任务队列配置 |
| `app.py` | 统一应用 | **修改** → 启动 TaskScheduler |

### 4.2 整合方案：最小化重构

**原则**：
- ✅ 保留现有接口（MCP 工具、REST API）
- ✅ 只修改内部实现
- ✅ 新增模块，尽量不删除现有代码（先共存，再迁移）

#### 4.2.1 新增模块

```
mcp-server/src/mineru_mcp/
├── task_queue/              # 新增目录
│   ├── __init__.py
│   ├── database.py          # SQLite 操作
│   ├── processor.py         # 任务处理器（调用 aio_do_parse）
│   ├── scheduler.py         # 任务调度器（clock）
│   └── file_manager.py      # 文件管理（保存到持久化目录）
├── mineru_client.py         # 保留（暂时共存，后期删除）
├── server.py                # 重构 MCP 工具实现
├── api.py                   # 重构 REST API 实现
├── concurrency.py           # 复用
├── config.py                # 扩展配置
└── app.py                   # 修改启动
```

#### 4.2.2 新增模块详解

**database.py**：SQLite 操作封装

```python
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List

class TaskDatabase:
    def __init__(self, db_path: str = "output/tasks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        
    def _init_tables(self):
        """初始化表结构"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                task_dir TEXT NOT NULL,
                input_filename TEXT NOT NULL,
                backend TEXT DEFAULT 'vlm-auto-engine',
                lang TEXT DEFAULT 'ch',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                timeout_seconds INTEGER DEFAULT 3600,
                error TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at);
        """)
        conn.commit()
        conn.close()
        
    def create_task(self, task_id: str, task_dir: str, input_filename: str, **options):
        """创建任务"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO tasks (task_id, task_dir, input_filename, backend, lang)
            VALUES (?, ?, ?, ?, ?)
        """, (task_id, task_dir, input_filename, options.get('backend', 'vlm-auto-engine'), options.get('lang', 'ch')))
        conn.commit()
        conn.close()
        
    def update_status(self, task_id: str, status: str, **extra):
        """更新任务状态"""
        conn = sqlite3.connect(self.db_path)
        fields = {"status": status}
        if status == "processing":
            fields["started_at"] = datetime.now().isoformat()
        elif status in ("completed", "failed"):
            fields["completed_at"] = datetime.now().isoformat()
        if "error" in extra:
            fields["error"] = extra["error"]
        
        sql = f"UPDATE tasks SET {', '.join(f'{k}=?' for k in fields)} WHERE task_id=?"
        conn.execute(sql, (*fields.values(), task_id))
        conn.commit()
        conn.close()
        
    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """查询一条记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return dict(row) if row else None
        
    def fetch_all(self, sql: str, params: tuple = ()) -> List[dict]:
        """查询多条记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]
```

**processor.py**：任务处理器

```python
import asyncio
from pathlib import Path
from mineru.cli.common import aio_do_parse, read_fn
from .database import TaskDatabase

class TaskProcessor:
    def __init__(self, db: TaskDatabase, config: dict):
        self.db = db
        self.semaphore = asyncio.Semaphore(config.get('max_concurrent', 3))
        self.active_tasks: dict[str, asyncio.Task] = {}
        
    async def process_task(self, task_id: str, task_data: dict):
        """处理单个任务"""
        # 创建 asyncio.Task 并记录
        task = asyncio.create_task(self._process_internal(task_id, task_data))
        self.active_tasks[task_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            self.db.update_status(task_id, "failed", error="Cancelled")
        except Exception as e:
            self.db.update_status(task_id, "failed", error=str(e))
        finally:
            # 清理 active_tasks
            self.active_tasks.pop(task_id, None)
            
    async def _process_internal(self, task_id: str, task_data: dict):
        """内部处理逻辑（使用 Semaphore）"""
        async with self.semaphore:
            # 准备参数
            task_dir = Path(task_data['task_dir'])
            input_file = task_dir / task_data['input_filename']
            pdf_name = Path(task_data['input_filename']).stem
            
            # 读取文件
            pdf_bytes = read_fn(input_file)
            
            # 调用 MinerU 核心
            await aio_do_parse(
                output_dir=str(task_dir),
                pdf_file_names=[pdf_name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=[task_data.get('lang', 'ch')],
                backend=task_data.get('backend', 'vlm-auto-engine'),
            )
            
            # 成功
            self.db.update_status(task_id, "completed")
            
    def cancel_task(self, task_id: str):
        """取消任务"""
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
```

**scheduler.py**：任务调度器（clock）

```python
import asyncio
from .database import TaskDatabase
from .processor import TaskProcessor

class TaskScheduler:
    def __init__(self, processor: TaskProcessor, db: TaskDatabase, config: dict):
        self.processor = processor
        self.db = db
        self.config = config
        self._running = False
        
    async def start(self):
        """启动调度器"""
        self._running = True
        asyncio.create_task(self._poll_loop())
        
    async def stop(self):
        """停止调度器"""
        self._running = False
        
    async def _poll_loop(self):
        """定时轮询（clock）：领取任务 + 检查超时"""
        while self._running:
            await asyncio.sleep(1)
            
            # 1. 领取待处理任务
            await self._fetch_pending_tasks()
            
            # 2. 检查超时任务
            await self._check_timeout_tasks()
            
    async def _fetch_pending_tasks(self):
        """领取待处理任务"""
        active_count = len(self.processor.active_tasks)
        max_concurrent = self.config.get('max_concurrent', 3)
        
        if active_count < max_concurrent:
            task = self.db.fetch_one("""
                SELECT * FROM tasks 
                WHERE status = 'pending' 
                ORDER BY created_at ASC 
                LIMIT 1
            """)
            
            if task:
                # 更新状态
                self.db.update_status(task['task_id'], 'processing')
                # 启动处理
                await self.processor.process_task(task['task_id'], task)
                
    async def _check_timeout_tasks(self):
        """检查超时任务"""
        import datetime
        now = datetime.datetime.now()
        
        timeout_tasks = self.db.fetch_all("""
            SELECT task_id, started_at, timeout_seconds 
            FROM tasks 
            WHERE status = 'processing' AND started_at IS NOT NULL
        """)
        
        for task in timeout_tasks:
            started_at = datetime.datetime.fromisoformat(task['started_at'])
            elapsed = (now - started_at).total_seconds()
            
            if elapsed > task['timeout_seconds']:
                # 超时，取消任务
                self.processor.cancel_task(task['task_id'])
                self.db.update_status(task['task_id'], 'failed', error='Timeout')
```

**file_manager.py**：文件管理

```python
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import UploadFile

class FileManager:
    def __init__(self, output_root: str = "output"):
        self.output_root = Path(output_root)
        
    def save_upload_file(self, file: UploadFile) -> tuple[str, Path]:
        """保存上传文件到持久化目录"""
        task_id = str(uuid.uuid4())
        today = datetime.now()
        
        # 创建日期分层目录
        task_dir = self.output_root / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存文件
        input_filename = f"input{Path(file.filename).suffix if file.filename else '.pdf'}"
        input_path = task_dir / input_filename
        
        content = file.file.read()
        input_path.write_bytes(content)
        
        return task_id, task_dir, input_filename
```

#### 4.2.3 重构现有模块

**server.py（MCP 工具）**：修改实现，保留接口

```python
# 修改前：调用 mineru_client.py
from mineru_mcp.mineru_client import get_client

@mcp.tool()
async def parse_pdf(file_path: str, ...):
    client = get_client()
    result = await client.parse_pdf_sync(file_path, ...)
    return result

# 修改后：调用任务队列
from mineru_mcp.task_queue import TaskDatabase, FileManager

@mcp.tool()
async def parse_pdf(file_path: str, ...):
    """同步解析（提交任务 + 等待完成）"""
    db = TaskDatabase()
    file_manager = FileManager()
    
    # 1. 提交任务
    task_id, task_dir, input_filename = file_manager.save_upload_file(...)
    db.create_task(task_id, task_dir, input_filename, ...)
    
    # 2. 等待完成
    while True:
        task = db.get_task(task_id)
        if task['status'] in ('completed', 'failed'):
            break
        await asyncio.sleep(1)
    
    # 3. 返回结果
    if task['status'] == 'completed':
        return {"markdown": "..."}
    else:
        raise ValueError(task['error'])
```

**api.py（REST API）**：修改实现，保留接口

```python
# 修改前：调用 mineru_client.py
@app.post("/parse")
async def parse_pdf_sync(file: UploadFile, ...):
    temp_path = _save_upload_file(file)
    client = get_client()
    result = await client.parse_pdf_sync(str(temp_path), ...)
    return result

# 修改后：调用任务队列
from mineru_mcp.task_queue import TaskDatabase, FileManager

@app.post("/parse")
async def parse_pdf_sync(file: UploadFile, ...):
    """同步解析"""
    file_manager = FileManager()
    task_id, task_dir, input_filename = file_manager.save_upload_file(file)
    
    db = TaskDatabase()
    db.create_task(task_id, task_dir, input_filename, backend=backend, ...)
    
    # 等待完成
    while True:
        task = db.get_task(task_id)
        if task['status'] in ('completed', 'failed'):
            break
        await asyncio.sleep(1)
    
    # 返回结果
    if task['status'] == 'completed':
        return {"task_id": task_id, "result": "..."}
    else:
        raise HTTPException(500, task['error'])
```

**app.py**：启动 TaskScheduler

```python
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # 启动任务调度器
    from mineru_mcp.task_queue import TaskDatabase, TaskProcessor, TaskScheduler
    
    db = TaskDatabase()
    processor = TaskProcessor(db, config)
    scheduler = TaskScheduler(processor, db, config)
    
    await scheduler.start()  # 启动 clock
    
    yield
    
    await scheduler.stop()   # 停止 clock
```

---

## 5. 整合后的架构

```
┌─────────────────────────────────────────────────────────┐
│             MCP Server (Single Process)                 │
│                                                         │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  REST API  │  │  MCP Tools   │  │ TaskScheduler  │  │
│  │  (api.py)  │  │  (server.py) │  │ (clock, 1秒)   │  │
│  └────────────┘  └──────────────┘  └────────────────┘  │
│         │                │                  │          │
│         └────────────────┴──────────────────┘          │
│                         │                               │
│                ┌────────────────┐                       │
│                │ TaskProcessor  │                       │
│                │  (aio_do_parse)│                       │
│                │  + Semaphore   │                       │
│                └────────────────┘                       │
│                         │                               │
│         ┌────────────────────────────────┐             │
│         │  SQLite (tasks.db) + Files     │             │
│         │  output/2026/05/10/{uuid}/...  │             │
│         └────────────────────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

**关键流程**：
- API/MCP 工具 → 提交任务到数据库
- TaskScheduler (clock) → 每秒轮询领取任务 + 检查超时
- TaskProcessor → 直接调用 MinerU 核心（`aio_do_parse()`）

---

## 6. 总结：简化后的方案

| 问题 | 用户建议 | 最终方案 |
|------|---------|---------|
| MinerU 输出路径 | 是否需要 `{pdf_name}/vlm/`？ | **遵循 MinerU 默认行为**（无法改变） |
| 并发控制 | 检查活跃数 < max，然后领取 | **clock 里检查 + 领取** ✅ |
| 超时机制 | 在 clock 里检查 | **clock 里检查超时 + 取消** ✅ |
| 架构整合 | 展开说明 | **新增模块 + 最小化重构** ✅ |

**优势**：
- ✅ 简化设计，逻辑集中（都在 clock）
- ✅ 最小化重构（保留接口）
- ✅ 渐进式迁移（先共存，再删除）

**✌Bazinga！**