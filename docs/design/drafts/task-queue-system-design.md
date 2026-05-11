# MinerU MCP Server 任务队列系统设计方案

## 1. 概述

基于 SQLite 的任务队列系统，直接调用 MinerU 核心函数 `aio_do_parse()`，支持文件上传、异步处理、并发控制、超时管理、认证保护。

**架构定位**：MCP Server 完全管理任务队列，不依赖 MinerU FastAPI 任务队列。

**调研基础**：基于 MinerU 源码调研（详见 `docs/mineru/mineru-task-queue-analysis.md`）。

**实施状态**：Phase 1-2 已完成（核心功能 + MCP 工具 + 认证集成）。

## 2. 目录结构

```
output/
├── 2026/
│   ├── 05/
│   │   ├── 10/
│   │   │   ├── {uuid-1}/
│   │   │   │   ├── input.pdf          # 上传的原始文件
│   │   │   │   └── {pdf_name}/vlm/    # MinerU 输出目录（MinerU 自动创建）
│   │   │   │       ├── {pdf_name}.md
│   │   │   │       ├── {pdf_name}_middle.json
│   │   │   │       ├── {pdf_name}_content_list.json
│   │   │   │       └── images/
│   │   │   │           ├── image_001.jpg
│   │   │   │           └── image_002.png
│   │   │   ├── {uuid-2}/
│   │   │   │   └── ...
├── tasks.db  # SQLite 数据库（任务队列）
```

**说明**：
- MinerU 输出路径由 MinerU 决定：`{task_dir}/{pdf_name}/{backend_type}/`
- `pdf_name` = 从 `input.pdf` 提取文件名（去掉扩展名）
- `backend_type` = `vlm`, `pipeline`, `hybrid_vlm` 等（由 backend 决定）

## 3. 数据库设计

### 3.1 任务队列表 (tasks)

**基于 MinerU AsyncParseTask 结构设计**：

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,           -- UUID
    status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed, cancelled
    task_dir TEXT NOT NULL,                 -- 任务目录: output/2026/05/10/{uuid}/
    input_filename TEXT NOT NULL,           -- 输入文件名: input.pdf
    
    -- MinerU 解析参数（复用 AsyncParseTask 字段）
    backend TEXT DEFAULT 'vlm-auto-engine',
    parse_method TEXT DEFAULT 'auto',
    lang_list TEXT DEFAULT '["ch"]',        -- JSON array
    formula_enable INTEGER DEFAULT 1,
    table_enable INTEGER DEFAULT 1,
    image_analysis INTEGER DEFAULT 1,
    server_url TEXT,                        -- VLM server URL (http-client backend)
    
    -- 输出选项（复用 AsyncParseTask 字段）
    return_md INTEGER DEFAULT 1,
    return_middle_json INTEGER DEFAULT 0,
    return_model_output INTEGER DEFAULT 0,
    return_content_list INTEGER DEFAULT 0,
    return_images INTEGER DEFAULT 0,
    response_format_zip INTEGER DEFAULT 0,
    return_original_file INTEGER DEFAULT 0,
    
    -- 页面范围（复用 AsyncParseTask 字段）
    start_page_id INTEGER DEFAULT 0,
    end_page_id INTEGER DEFAULT 99999,
    
    -- 时间管理
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,                   -- 开始处理时间
    completed_at TIMESTAMP,                  -- 完成时间
    timeout_at TIMESTAMP,                   -- 超时时间点
    timeout_seconds INTEGER DEFAULT 3600,   -- 超时时长（秒）
    
    -- 错误与重试
    error_message TEXT,                     -- 错误信息
    retry_count INTEGER DEFAULT 0,          -- 重试次数
    
    -- 结果摘要
    result_summary TEXT                     -- JSON 处理结果摘要
);

-- 约定:
-- 输入文件路径: {task_dir}{input_filename}
-- 输出目录路径: {task_dir}{pdf_name}/{backend_type}/  (MinerU 输出结构)
-- pdf_name: 从 input_filename 提取（去掉扩展名）
-- backend_type: vlm, pipeline, hybrid_vlm 等

CREATE INDEX idx_status ON tasks(status);
CREATE INDEX idx_created_at ON tasks(created_at);
CREATE INDEX idx_timeout_at ON tasks(timeout_at);
```

### 3.2 系统配置（.env 文件）

配置通过环境变量管理，便于部署和修改：

```bash
# 任务队列配置
MINERU_MAX_CONCURRENT=3        # 最大并发处理数
MINERU_TASK_TIMEOUT=3600       # 任务超时时间（秒）
MINERU_RETRY_LIMIT=3           # 最大重试次数
MINERU_CLEANUP_DAYS=30         # 清理多少天前的已完成任务

# 数据库配置
MINERU_DB_PATH=/app/output/tasks.db

# 日志配置
MINERU_LOG_LEVEL=INFO

# 认证配置（可选）
# 未设置：认证禁用（所有端点无需认证）
# 已设置：认证启用（所有端点需要 Bearer token）
MCP_HTTP_AUTH_TOKEN=your-secure-token-here  # 设置后启用认证
```

> 后续有网页管理界面时，可迁移到数据库 config 表，支持动态配置。

### 3.3 认证机制

**Bearer Token 认证**：

```bash
# 生成 token
python -m mineru_mcp.auth
# 或
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 设置到 .env
MCP_HTTP_AUTH_TOKEN=<generated_token>
```

**使用方式**：

```bash
# HTTP 请求
curl -H "Authorization: Bearer <token>" http://localhost:8001/mcp

# 无 token（认证禁用时）
curl http://localhost:8001/mcp  # ✅ 正常响应

# 有 token（认证启用时）
curl http://localhost:8001/mcp  # ❌ 401 Unauthorized
curl -H "Authorization: Bearer <token>" http://localhost:8001/mcp  # ✅ 正常响应
```

**认证绕过**：
- `/`, `/health` 端点无需认证
- OPTIONS 请求无需认证

### 3.4 处理日志表 (task_logs)

```sql
CREATE TABLE task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    level TEXT NOT NULL,        -- INFO, WARNING, ERROR
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX idx_task_id ON task_logs(task_id);
```

## 4. 核心工作流程

### 4.1 MinerU 集成方式

**直接调用 MinerU 核心函数**：

```python
from mineru.cli.common import aio_do_parse, read_fn
from pathlib import Path

async def process_task(task_id: str, file_path: str, options: dict):
    """直接调用 MinerU 核心，不启动 FastAPI"""
    # 异步读取文件（避免阻塞）
    pdf_bytes = await asyncio.to_thread(read_fn, Path(file_path))
    pdf_name = Path(file_path).stem
    output_dir = f"./output/{task_id}"
    
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
```

**优势**：
- ✅ 无 HTTP 开销，性能更优
- ✅ 完全控制任务生命周期（包括超时取消）
- ✅ MinerU 内存队列的缺陷（重启丢失）被 SQLite 持久化弥补

**MinerU 调研发现**：
- MinerU 任务队列：内存字典，重启丢失
- MinerU 并发控制：asyncio.Semaphore（可直接复用）
- MinerU 缺少超时取消：客户端超时仅抛异常，任务继续运行
- MinerU 核心函数：`aio_do_parse()` 可直接调用

### 4.2 文件上传流程

```
客户端上传文件
    ↓
生成 UUID
    ↓
计算日期路径: output/YYYY/MM/DD/{uuid}/
    ↓
保存文件到 {uuid}/input.{ext}
    ↓
插入 tasks 表 (task_dir, input_filename, status=pending)
    ↓
返回 task_id 给客户端
```

### 4.3 任务处理流程

```
Scheduler (clock, 每秒轮询)
    ↓
检查：active_count < max_concurrent ?
    ↓
是 → 查询 tasks 表
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT (max_concurrent - active_count)
    ↓
CAS（Compare-And-Swap）原子更新：
    UPDATE tasks 
    SET status = 'processing', started_at = NOW()
    WHERE status = 'pending' AND task_id = ?
    ↓
检查 rowcount > 0 ?（确认领取成功）
    ↓
是 → 创建 asyncio.Task，使用回调处理错误
    ↓
调用 aio_do_parse()（MinerU 核心函数）
    ↓
成功: status = 'completed', completed_at = NOW()
失败: status = 'failed', error_message = ...
超时: asyncio.Task.cancel(), status = 'failed', error = 'Timeout'
```

**关键改进**：
- 使用 CAS 原子更新避免竞争条件
- 回调方式处理错误（不阻塞 scheduler）
- `read_fn` 异步包装（`asyncio.to_thread`）

### 4.4 超时处理流程

**Scheduler 检查超时任务（每秒）**：

```
查询 tasks 表
    WHERE status = 'processing' AND started_at + timeout_seconds < NOW()
    ↓
找到对应的 asyncio.Task 对象
    ↓
调用 task.cancel()（主动取消）
    ↓
更新 status = 'failed', error_message = 'Timeout'
    ↓
释放并发槽位
```

**实现代码**：

```python
async def _check_timeout_tasks(self):
    """检查超时任务"""
    now = datetime.now()
    
    processing_tasks = self.db.fetch_all(
        "SELECT task_id, started_at, timeout_seconds FROM tasks WHERE status = 'processing'"
    )
    
    for task_data in processing_tasks:
        started_at = datetime.fromisoformat(task_data['started_at'])
        elapsed = (now - started_at).total_seconds()
        
        if elapsed > task_data['timeout_seconds']:
            # 超时，取消任务
            self.processor.cancel_task(task_data['task_id'])
            self.db.update_status(task_data['task_id'], 'failed', error='Timeout')
```

### 4.5 容器重启恢复流程

```
服务启动时
    ↓
查询 tasks 表
    WHERE status = 'processing'
    ↓
重置为 status = 'pending', retry_count += 1
    ↓
超过 retry_limit 的标记为 status = 'failed'
```

## 5. 并发控制实现

### 5.1 MinerU Semaphore 复用

**复用 MinerU 的并发控制模式**：

```python
class TaskProcessor:
    def __init__(self, db: TaskDatabase, max_concurrent: int = 3):
        self.db = db
        # 复用 MinerU 的 Semaphore 并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: dict[str, asyncio.Task] = {}
        
    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """任务完成回调（不阻塞）"""
        try:
            task.result()
        except asyncio.CancelledError:
            self.db.update_status(task_id, "cancelled", error="Cancelled")
        except Exception as e:
            self.db.update_status(task_id, "failed", error=str(e))
        finally:
            self.active_tasks.pop(task_id, None)
    
    async def process_task(self, task_id: str, task_data: dict):
        """处理任务（不阻塞调用者）"""
        task = asyncio.create_task(self._process_internal(task_id, task_data))
        self.active_tasks[task_id] = task
        task.add_done_callback(lambda t: self._on_task_done(task_id, t))
```

### 5.2 任务调度逻辑

```python
async def _poll_loop(self):
    """任务调度循环（clock）"""
    while self._running:
        await asyncio.sleep(self.poll_interval)
        
        # 1. 领取待处理任务
        await self._fetch_pending_tasks()
        
        # 2. 检查超时任务
        await self._check_timeout_tasks()

async def _fetch_pending_tasks(self):
    """领取待处理任务（CAS）"""
    active_count = self.processor.get_active_count()
    
    if active_count >= self.max_concurrent:
        return
    
    available_slots = self.max_concurrent - active_count
    tasks = self.db.fetch_all(
        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (available_slots,)
    )
    
    for task_data in tasks:
        # CAS 原子更新
        updated = self.db.execute(
            "UPDATE tasks SET status = 'processing', started_at = ? WHERE status = 'pending' AND task_id = ?",
            (datetime.now().isoformat(), task_data['task_id'])
        )
        
        if updated > 0:
            # 领取成功
            asyncio.create_task(self.processor.process_task(task_data['task_id'], task_data))
```

## 6. API 接口设计

### 6.1 上传文件

```
POST /api/v1/tasks/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>  # 认证启用时需要

Request:
  file: <binary>
  backend: "hybrid-http-client" (optional)
  options: { ... } (optional, JSON string)

Response:
{
    "task_id": "uuid",
    "status": "pending",
    "created_at": "2026-05-10T11:00:00Z"
}
```

### 6.2 查询任务状态

```
GET /api/v1/tasks/{task_id}
Authorization: Bearer <token>  # 认证启用时需要

Response:
{
    "task_id": "uuid",
    "status": "processing",
    "created_at": "2026-05-10T11:00:00Z",
    "started_at": "2026-05-10T11:00:05Z",
    "error": null
}
```

### 6.3 获取任务列表

```
GET /api/v1/tasks?status=pending&limit=20&offset=0
Authorization: Bearer <token>  # 认证启用时需要

Response:
{
    "total": 100,
    "tasks": [...]
}
```

### 6.4 查询系统配置

```
GET /api/v1/config
Authorization: Bearer <token>  # 认证启用时需要

Response:
{
    "max_concurrent": 3,
    "task_timeout": 3600,
    "retry_limit": 3,
    "cleanup_days": 30,
    "auth_required": true  # 认证是否启用
}
```

### 6.5 健康检查

```
GET /health
# 无需认证

Response:
{
    "status": "healthy",
    "uptime": 3600
}
```

## 7. 配置管理

所有系统配置通过环境变量管理，从 `.env` 文件加载。

### 7.1 配置读取

```python
class Config:
    def __init__(self):
        self.max_concurrent = int(os.getenv('MINERU_MAX_CONCURRENT', '3'))
        self.task_timeout = int(os.getenv('MINERU_TASK_TIMEOUT', '3600'))
        self.retry_limit = int(os.getenv('MINERU_RETRY_LIMIT', '3'))
        self.cleanup_days = int(os.getenv('MINERU_CLEANUP_DAYS', '30'))
        self.db_path = os.getenv('MINERU_DB_PATH', '/app/output/tasks.db')
        self.log_level = os.getenv('MINERU_LOG_LEVEL', 'INFO')
        self.http_auth_token = os.getenv('MCP_HTTP_AUTH_TOKEN')  # None = 认证禁用
```

## 8. 监控与维护

### 8.1 监控指标

- 当前待处理任务数
- 当前处理中任务数
- 平均处理时间
- 成功率/失败率
- 超时任务数
- 认证是否启用

### 8.2 定期清理

```python
def cleanup_old_tasks():
    """清理旧任务数据"""
    cleanup_days = get_config('cleanup_days', 30)
    cutoff_date = datetime.now() - timedelta(days=cleanup_days)
    
    # 查询旧任务
    old_tasks = db.fetch_all("""
        SELECT task_id, task_dir 
        FROM tasks 
        WHERE status IN ('completed', 'failed') 
        AND completed_at < ?
    """, (cutoff_date,))
    
    # 删除文件目录
    for task in old_tasks:
        task_dir = Path(task['task_dir'])
        shutil.rmtree(task_dir, ignore_errors=True)
    
    # 删除数据库记录
    db.execute("""
        DELETE FROM tasks 
        WHERE status IN ('completed', 'failed') 
        AND completed_at < ?
    """, (cutoff_date,))
```

## 9. 错误处理与重试策略

### 9.1 重试策略

| 场景 | 处理方式 |
|------|---------|
| 处理超时 | 自动重试，最多 3 次 |
| 进程崩溃 | 容器重启时自动恢复 |
| 临时错误 (网络) | 指数退避重试 |
| 永久错误 (文件损坏) | 标记失败，不重试 |

### 9.2 错误分类

```python
class TaskError(Exception):
    RETRYABLE = True
    
class TimeoutError(TaskError):
    RETRYABLE = True

class FileNotFoundError(TaskError):
    RETRYABLE = False

class CorruptedFileError(TaskError):
    RETRYABLE = False
```

## 10. 部署架构

### 10.1 单容器部署（含认证）

```
┌──────────────────────────────────────────────────┐
│          MCP Server Container                     │
│                                                   │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ REST API   │  │ MCP Tools   │  │ Scheduler│  │
│  │ (api.py)   │  │ (server.py) │  │ (clock)  │  │
│  └────────────┘  └─────────────┘  └──────────┘  │
│         │                │                 │     │
│         └────────────────┴─────────────────┘     │
│                           │                       │
│                  ┌────────────────┐              │
│                  │ AuthMiddleware │              │
│                  │ (Bearer Token) │              │
│                  └────────────────┘              │
│                           │                       │
│         ┌────────────────────────────────┐      │
│         │  SQLite + File + Auth Config   │      │
│         └────────────────────────────────┘      │
└──────────────────────────────────────────────────┘
```

**认证流程**：
- 客户端请求 → AuthMiddleware → 验证 Bearer token
- 健康检查端点 `/`, `/health` → 绕过认证
- 其他端点 → 需要 `Authorization: Bearer <token>`

### 10.2 扩展性考虑

未来可扩展为：
- 多 Worker 进程
- 外部队列 (Redis/RabbitMQ)
- 分布式存储 (MinIO/S3)
- 动态认证管理（数据库 token 表）

## 11. 实施步骤

### 阶段一：核心功能 (优先级 P0) ✅ 已完成

- [x] SQLite 数据库初始化（database.py）
- [x] 任务队列表结构（WAL 模式）
- [x] 文件管理（file_manager.py，日期分层）
- [x] 任务处理器（processor.py，直接调用 aio_do_parse）
- [x] 任务调度器（scheduler.py，clock + 超时检查）
- [x] 配置管理（config.py 扩展）
- [x] 代码审计修复（P0 Critical Issues）

### 阶段二：MCP 工具与认证 (优先级 P0) ✅ 已完成

- [x] MCP 工具重构（server_task_queue.py）
- [x] 认证模块集成（AuthMiddleware）
- [x] 认证测试（test_auth_integration.py）
- [x] 双模式切换（task_queue_enabled）
- [x] .env.example 更新（认证说明）

### 阶段三：REST API 重构 (优先级 P1) 🚧 进行中

- [ ] REST API 重构（api_task_queue.py）
- [ ] 认证应用到 API 端点
- [ ] 完整集成测试

### 阶段四：监控与维护 (优先级 P2)

- [ ] 监控指标 API
- [ ] 定期清理脚本
- [ ] 错误日志记录

## 12. 代码审计修复记录

### P0 Critical Issues（已修复）

| 问题 | 文件 | 修复 |
|------|------|------|
| datetime.timedelta 缺失 | database.py:286 | 导入 `timedelta` |
| read_fn 同步阻塞 | processor.py:89 | `asyncio.to_thread` 包装 |
| process_task await 阻塞 | processor.py:55-67 | 回调方式，不阻塞 |
| PRAGMA 位置不当 | database.py:86-87 | 移到 `_conn()` 方法 |
| 状态更新竞争 | scheduler.py:120 | CAS 原子更新 |

详见：`docs/design/drafts/code-audit-report.md`

## 13. 总结

### 13.1 MinerU 调研发现

| MinerU 特性 | MCP Server 方案 | 说明 |
|-------------|----------------|------|
| 内存存储（重启丢失） | SQLite 持久化 ✅ | 解决重启丢失问题 |
| asyncio.Semaphore | 直接复用 ✅ | MinerU 并发控制模式简单有效 |
| 缺少超时取消 | 增加 `asyncio.Task.cancel()` ✅ | MinerU 缺陷，方案补充 |
| `aio_do_parse()` 可直接调用 | 直接调用 ✅ | 无 HTTP 开销，性能更优 |
| 无日期分层 | 方案增加 ✅ | `output/2026/05/10/{uuid}/` |
| 无认证机制 | Bearer Token ✅ | 方案新增，可选启用 |

### 13.2 方案优势

**对比 MinerU FastAPI 任务队列**：

| 维度 | MinerU FastAPI 队列 | MCP Server 方案 |
|------|---------------------|-----------------|
| 存储方式 | 内存字典 | SQLite 持久化 ✅ |
| 重启恢复 | 任务丢失 ❌ | 任务状态保留 ✅ |
| 超时取消 | 无机制 ❌ | `asyncio.Task.cancel()` ✅ |
| HTTP 开销 | 有 ❌ | 无（直接调用） ✅ |
| 并发控制 | Semaphore ✅ | Semaphore（复用） ✅ |
| 文件路径 | task_id 目录 | 日期分层目录 ✅ |
| 认证机制 | 无 ❌ | Bearer Token（可选） ✅ |

### 13.3 实施建议

**当前进度**：
- Phase 1-2 已完成 ✅
- Phase 3 进行中 🚧
- Phase 4 待实施 ⏳

**推荐优先级**：
1. ✅ P0（核心功能 + MCP 工具 + 认证）
2. 🚧 P1（REST API 重构）
3. ⏳ P2（监控清理）

**✌Bazinga！**