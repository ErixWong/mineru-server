# MinerU 任务队列实现分析

## 1. FastAPI 实现

### 1.1 主文件位置

- **路径**: `MinerU/mineru/cli/fast_api.py`
- **启动命令**: `mineru-api` 或 `python -m mineru.cli.fast_api`

### 1.2 API 端点

| 端点 | 方法 | 功能 | 状态码 |
|------|------|------|--------|
| `/file_parse` | POST | 同步解析，等待结果返回 | 200 |
| `/tasks` | POST | 异步提交任务，立即返回 task_id | 202 |
| `/tasks/{task_id}` | GET | 查询任务状态 | 200 |
| `/tasks/{task_id}/result` | GET | 获取任务结果 | 200/202 |
| `/health` | GET | 健康检查 | 200/503 |

### 1.3 `/tasks` 端点实现

```python
# fast_api.py 第 1452-1469 行
@app.post(path="/tasks", status_code=202)
async def submit_parse_task(http_request: Request, request_options: ParseRequestOptions):
    task_manager = get_task_manager()
    task = await create_async_parse_task(request_options)
    return build_task_submission_response(task, http_request, task_manager)
```

**流程**:
1. 解析请求参数（文件、语言、backend等）
2. 生成 UUID 作为 task_id
3. 保存上传文件到 `{output_root}/{task_id}/uploads/`
4. 创建 `AsyncParseTask` 对象
5. 提交到 `AsyncTaskManager` 的队列
6. 返回 202 响应，包含 task_id、status_url、result_url

### 1.4 `/file_parse` 端点实现

```python
# fast_api.py 第 1404-1449 行
@app.post(path="/file_parse", status_code=200)
async def parse_pdf(http_request: Request, background_tasks: BackgroundTasks, request_options: ParseRequestOptions):
    task = await create_async_parse_task(request_options)
    task_manager = get_task_manager()
    
    # 等待任务完成
    task = await task_manager.wait_for_terminal_state(task.task_id)
    
    if task.status == TASK_FAILED:
        return JSONResponse(status_code=409, content={...})
    
    return await build_sync_file_parse_response(background_tasks, task, http_request)
```

**流程**:
1. 同样创建异步任务
2. **阻塞等待**任务完成（使用 `wait_for_terminal_state`）
3. 返回结果（JSON 或 ZIP）

---

## 2. 任务队列机制

### 2.1 核心类：AsyncTaskManager

```python
# fast_api.py 第 1102-1395 行
class AsyncTaskManager:
    def __init__(self, fastapi_app: FastAPI):
        self.app = fastapi_app
        self.tasks: dict[str, AsyncParseTask] = {}         # 所有任务存储
        self.task_events: dict[str, asyncio.Event] = {}    # 任务完成事件
        self.queue: asyncio.Queue[str] = asyncio.Queue()   # 任务队列
        self.dispatcher_task: Optional[asyncio.Task] = None  # 分发协程
        self.cleanup_task: Optional[asyncio.Task] = None   # 清理协程
        self.active_tasks: set[asyncio.Task] = set()       # 正在执行的任务
        self._next_submit_order = 1                        # 提交顺序计数
```

### 2.2 任务状态

```python
# fast_api.py 第 79-83 行
TASK_PENDING = "pending"      # 等待处理
TASK_PROCESSING = "processing"  # 正在处理
TASK_COMPLETED = "completed"   # 完成
TASK_FAILED = "failed"         # 失败
TASK_TERMINAL_STATES = {TASK_COMPLETED, TASK_FAILED}
```

### 2.3 任务数据结构

```python
# fast_api.py 第 169-198 行
@dataclass
class AsyncParseTask:
    task_id: str
    status: str
    backend: str
    file_names: list[str]
    created_at: str
    output_dir: str
    parse_method: str
    lang_list: list[str]
    formula_enable: bool
    table_enable: bool
    image_analysis: bool
    server_url: Optional[str]
    return_md: bool
    return_middle_json: bool
    return_model_output: bool
    return_content_list: bool
    return_images: bool
    response_format_zip: bool
    return_original_file: bool
    start_page_id: int
    end_page_id: int
    upload_names: list[str]
    uploads: list[str]          # 上传文件路径
    submit_order: int = 0       # 提交顺序
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
```

### 2.4 任务分发流程

```python
# fast_api.py 第 1272-1289 行
async def _dispatcher_loop(self):
    while True:
        task_id = await self.queue.get()
        processor = asyncio.create_task(self._process_task(task_id))
        self.active_tasks.add(processor)
        processor.add_done_callback(self._on_processor_done)
        self.queue.task_done()
```

**关键点**:
1. 从队列获取 task_id
2. 创建处理协程
3. 加入 active_tasks 集合
4. 协程完成后回调处理

### 2.5 任务处理流程

```python
# fast_api.py 第 1312-1331 行
async def _process_task(self, task_id: str):
    task = self.tasks.get(task_id)
    try:
        if _request_semaphore is not None:
            async with _request_semaphore:  # 并发控制
                await self._run_task(task)
        else:
            await self._run_task(task)
    except Exception as exc:
        task.status = TASK_FAILED
        task.error = str(exc)
        task.completed_at = utc_now_iso()
        self._signal_task_event(task_id)
```

### 2.6 数据库使用

**重要结论**: MinerU **不使用 SQLite 或任何数据库**。

- 所有任务存储在内存字典 `self.tasks` 中
- 任务数据在服务重启后丢失
- 这是一种轻量级设计，适合单机部署

---

## 3. 并发控制

### 3.1 信号量机制

```python
# fast_api.py 第 102-104 行
_request_semaphore: Optional[asyncio.Semaphore] = None
_configured_max_concurrent_requests = 1

# fast_api.py 第 249-262 行（create_app 中）
max_concurrent_requests = read_max_concurrent_requests(default=DEFAULT_MAX_CONCURRENT_REQUESTS)
_request_semaphore = asyncio.Semaphore(max_concurrent_requests)
```

### 3.2 默认并发配置

```python
# api_protocol.py 第 3 行
DEFAULT_MAX_CONCURRENT_REQUESTS = 3

# config_reader.py 第 142-162 行
def get_max_concurrent_requests(default: int = 3) -> int:
    value = os.getenv('MINERU_API_MAX_CONCURRENT_REQUESTS')
    if value is None:
        return default
    return int(value)
```

### 3.3 Mac 环境特殊限制

```python
# fast_api.py 第 251-252 行
if is_mac_environment():
    max_concurrent_requests = 1
```

### 3.4 并发配置方式

| 配置方式 | 说明 |
|----------|------|
| 环境变量 `MINERU_API_MAX_CONCURRENT_REQUESTS` | 直接设置并发数 |
| 配置文件 `~/mineru.json` | 可通过 `max_concurrent_requests` 字段配置 |
| Mac 环境 | 强制限制为 1 |

---

## 4. 文件存储方式

### 4.1 上传文件存储

```python
# fast_api.py 第 1055-1065 行
async def create_async_parse_task(request_options):
    task_id = str(uuid.uuid4())
    task_output_dir = create_task_output_dir(task_id)
    uploads_dir = os.path.join(task_output_dir, "uploads")
    uploads = await save_upload_files(uploads_dir, request_options.files)
```

**路径规则**:
```
{output_root}/{task_id}/uploads/{original_filename}
```

### 4.2 输出文件存储

```python
# common.py 第 175-180 行
def prepare_env(output_dir, pdf_file_name, parse_method):
    local_md_dir = str(os.path.join(output_dir, pdf_file_name, parse_method))
    local_image_dir = os.path.join(str(local_md_dir), "images")
    os.makedirs(local_image_dir, exist_ok=True)
    os.makedirs(local_md_dir, exist_ok=True)
    return local_image_dir, local_md_dir
```

**路径规则** (output_paths.py):
```python
# 不同 backend 的输出路径
pipeline:   {output_root}/{pdf_name}/{parse_method}/
vlm:        {output_root}/{pdf_name}/vlm/
hybrid:     {output_root}/{pdf_name}/hybrid_{parse_method}/
office:     {output_root}/{pdf_name}/office/
```

### 4.3 输出根目录

```python
# fast_api.py 第 88 行
DEFAULT_OUTPUT_ROOT = "./output"

# fast_api.py 第 363-366 行
def get_output_root() -> Path:
    root = Path(os.getenv("MINERU_API_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT)).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
```

**配置**: 环境变量 `MINERU_API_OUTPUT_ROOT`

### 4.4 日期分层

**结论**: MinerU **没有日期分层**存储。

- 文件直接按 `task_id` 或 `pdf_name` 组织
- 没有按日期创建子目录的逻辑
- 依赖任务清理机制来管理旧文件

### 4.5 完整存储结构示例

```
./output/                           # output_root (可配置)
├── {task_id_1}/                    # 任务目录
│   ├── uploads/                    # 上传文件
│   │   ├── document.pdf
│   │   └── image.png
│   ├── document/                   # 解析结果 (pdf_name)
│   │   ├── vlm/                    # backend 类型
│   │   │   ├── document.md         # Markdown 输出
│   │   │   ├── document_middle.json
│   │   │   ├── document_model.json
│   │   │   ├── document_content_list.json
│   │   │   └── images/             # 提取的图片
│   │   │       ├── image_001.jpg
│   │   │       └── image_002.png
├── {task_id_2}/
│   ├── uploads/
│   └── ...
```

---

## 5. 任务清理与超时管理

### 5.1 任务清理机制

```python
# fast_api.py 第 86-87 行
DEFAULT_TASK_RETENTION_SECONDS = 24 * 60 * 60      # 24 小时
DEFAULT_TASK_CLEANUP_INTERVAL_SECONDS = 5 * 60     # 5 分钟

# fast_api.py 第 1291-1301 行
async def _cleanup_loop(self):
    while True:
        await asyncio.sleep(self.task_cleanup_interval_seconds)
        self.cleanup_expired_tasks()
```

### 5.2 过期任务清理

```python
# fast_api.py 第 1360-1380 行
def cleanup_expired_tasks(self) -> int:
    if self.task_retention_seconds <= 0:
        return 0

    now = datetime.now(timezone.utc)
    expired_task_ids = [
        task_id for task_id, task in self.tasks.items()
        if self._is_task_expired(task, now)
    ]

    for task_id in expired_task_ids:
        task = self.tasks.pop(task_id, None)
        task_event = self.task_events.pop(task_id, None)
        if task_event is not None:
            task_event.set()
        cleanup_file(task.output_dir)  # 删除整个任务目录
```

**清理条件**:
- 任务状态为 `completed` 或 `failed`
- `completed_at` 时间超过 `task_retention_seconds`

### 5.3 超时配置一览

| 超时类型 | 默认值 | 环境变量 |
|----------|--------|----------|
| 任务结果等待 | 3600s (1h) | `MINERU_TASK_RESULT_TIMEOUT_SECONDS` |
| API 启动等待 | 300s (5min) | `MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS` |
| 结果下载 | 600s (10min) | `MINERU_TASK_RESULT_DOWNLOAD_TIMEOUT_SECONDS` |
| PDF 渲染 | 300s (5min) | `MINERU_PDF_RENDER_TIMEOUT` |
| HTTP 客户端请求 | 600s | `http_timeout` 参数 |
| 任务保留时间 | 86400s (24h) | `MINERU_API_TASK_RETENTION_SECONDS` |
| 清理检查间隔 | 300s (5min) | `MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS` |

### 5.4 超时任务处理

**关键发现**: MinerU **没有主动取消超时任务**的机制。

- `wait_for_task_result` 会等待超时后抛出异常
- 但任务本身不会被强制终止
- 任务如果执行时间过长，会一直占用并发槽位

```python
# api_client.py 第 931-986 行
async def wait_for_task_result(..., timeout_seconds: float = TASK_RESULT_TIMEOUT_SECONDS):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(submit_response.status_url)
        status = payload.get("status")
        if status in {"pending", "processing"}:
            await asyncio.sleep(TASK_STATUS_POLL_INTERVAL_SECONDS)
            continue
        if status == "completed":
            return
        raise click.ClickException(f"Task {task_id} failed...")
    
    raise click.ClickException(f"Timed out waiting for result...")
```

---

## 6. 核心解析函数

### 6.1 同步解析函数：do_parse

```python
# common.py 第 619-709 行
def do_parse(
    output_dir,
    pdf_file_names: list[str],
    pdf_bytes_list: list[bytes],
    p_lang_list: list[str],
    backend="pipeline",
    parse_method="auto",
    formula_enable=True,
    table_enable=True,
    server_url=None,
    f_draw_layout_bbox=True,
    f_draw_span_bbox=True,
    f_dump_md=True,
    f_dump_middle_json=True,
    f_dump_model_output=True,
    f_dump_orig_pdf=True,
    f_dump_content_list=True,
    f_make_md_mode=MakeMode.MM_MD,
    start_page_id=0,
    end_page_id=None,
    image_analysis=True,
    **kwargs,
):
```

### 6.2 异步解析函数：aio_do_parse

```python
# common.py 第 712-802 行
async def aio_do_parse(
    output_dir,
    pdf_file_names: list[str],
    pdf_bytes_list: list[bytes],
    p_lang_list: list[str],
    backend="pipeline",
    parse_method="auto",
    formula_enable=True,
    table_enable=True,
    server_url=None,
    ...
    **kwargs,
):
```

### 6.3 直接调用示例

**完全可以不通过 HTTP 直接调用**:

```python
from mineru.cli.common import do_parse, aio_do_parse, read_fn
from pathlib import Path

# 同步调用
pdf_path = "document.pdf"
pdf_bytes = read_fn(Path(pdf_path))
do_parse(
    output_dir="./output",
    pdf_file_names=["document"],
    pdf_bytes_list=[pdf_bytes],
    p_lang_list=["ch"],
    backend="vlm-auto-engine",
    parse_method="auto",
)

# 异步调用
import asyncio
asyncio.run(aio_do_parse(
    output_dir="./output",
    pdf_file_names=["document"],
    pdf_bytes_list=[pdf_bytes],
    p_lang_list=["ch"],
    backend="vlm-auto-engine",
))
```

### 6.4 Backend 类型

| Backend | 说明 | 同步支持 | 异步支持 |
|---------|------|----------|----------|
| `pipeline` | 传统 OCR + 布局分析 | Yes | No (用同步) |
| `vlm-auto-engine` | 本地 VLM 自动选择引擎 | Yes | Yes |
| `vlm-transformers` | HuggingFace Transformers | Yes | Yes |
| `vlm-vllm-engine` | vLLM 同步引擎 | Yes | No |
| `vlm-vllm-async-engine` | vLLM 异步引擎 | No | Yes |
| `vlm-lmdeploy-engine` | LMDeploy | Yes | Yes |
| `vlm-http-client` | 远程 HTTP 服务 | Yes | Yes |
| `hybrid-auto-engine` | 混合模式本地引擎 | Yes | Yes |
| `hybrid-http-client` | 混合模式远程服务 | Yes | Yes |

---

## 7. 与 MCP Server 任务队列方案契合度分析

### 7.1 MinerU 特点总结

| 特性 | MinerU 实现 | MCP Server 需求 |
|------|-------------|-----------------|
| 任务存储 | 内存字典，重启丢失 | 需持久化存储 |
| 并发控制 | Semaphore，全局限制 | 可借鉴 |
| 任务状态 | pending/processing/completed/failed | 可直接复用 |
| 任务清理 | 基于时间自动清理 | 可借鉴 |
| 超时处理 | 仅客户端超时，无任务取消 | 需增强 |
| 文件存储 | task_id 目录结构 | 可直接复用 |
| 直接调用 | 支持 `aio_do_parse` | **非常适合** |

### 7.2 契合度评估

#### 高契合点

1. **直接调用能力**:
   - `aio_do_parse` 可直接集成到 MCP Server
   - 无需启动 FastAPI 服务
   - 节省资源和启动时间

2. **状态模型一致**:
   - pending → processing → completed/failed
   - 与典型任务队列模型完全一致

3. **并发控制简单有效**:
   - Semaphore 机制轻量且可靠
   - 可直接复用代码

#### 需改进点

1. **持久化存储**:
   - MinerU 内存存储不适合 MCP Server
   - MCP Server 需要 SQLite 持久化
   - 任务状态需要跨重启保持

2. **超时任务取消**:
   - MinerU 没有主动取消机制
   - MCP Server 需要实现任务超时取消
   - 需要增加 `asyncio.Task.cancel()` 调用

3. **日期分层存储**:
   - MinerU 没有，但 MCP Server 可能需要
   - 方便按日期清理和检索

4. **任务优先级**:
   - MinerU 只有 FIFO 顺序
   - MCP Server 可能需要优先级队列

### 7.3 推荐集成方案

```python
# MCP Server 任务处理核心代码示例
import asyncio
from mineru.cli.common import aio_do_parse, read_fn

class MinerUTaskProcessor:
    def __init__(self, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: dict[str, asyncio.Task] = {}
    
    async def process_task(self, task_id: str, task_data: dict):
        async with self._semaphore:
            pdf_bytes = read_fn(task_data["file_path"])
            await aio_do_parse(
                output_dir=task_data["output_dir"],
                pdf_file_names=[task_data["file_name"]],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=[task_data["lang"]],
                backend=task_data["backend"],
                **task_data.get("options", {}),
            )
    
    def cancel_task(self, task_id: str):
        task = self._active_tasks.get(task_id)
        if task:
            task.cancel()
```

### 7.4 数据库表结构建议

基于 MinerU 的 `AsyncParseTask` 结构：

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,           -- UUID
    status TEXT NOT NULL,          -- pending/processing/completed/failed
    backend TEXT NOT NULL,
    file_names TEXT NOT NULL,      -- JSON array
    created_at TEXT NOT NULL,      -- ISO timestamp
    started_at TEXT,
    completed_at TEXT,
    output_dir TEXT NOT NULL,
    parse_method TEXT NOT NULL,
    lang_list TEXT NOT NULL,       -- JSON array
    formula_enable INTEGER DEFAULT 1,
    table_enable INTEGER DEFAULT 1,
    image_analysis INTEGER DEFAULT 1,
    return_options TEXT,           -- JSON object
    start_page_id INTEGER DEFAULT 0,
    end_page_id INTEGER DEFAULT 99999,
    upload_paths TEXT,             -- JSON array
    error TEXT,
    submit_order INTEGER,
    timeout_seconds INTEGER DEFAULT 3600,
    created_date TEXT,             -- YYYY-MM-DD for date partitioning
);
```

---

## 8. 环境变量完整列表

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MINERU_API_OUTPUT_ROOT` | `./output` | 输出根目录 |
| `MINERU_API_MAX_CONCURRENT_REQUESTS` | 3 | 最大并发数 |
| `MINERU_API_TASK_RETENTION_SECONDS` | 86400 | 任务保留时间 (24h) |
| `MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS` | 300 | 清理检查间隔 (5min) |
| `MINERU_TASK_RESULT_TIMEOUT_SECONDS` | 3600 | 任务结果等待超时 (1h) |
| `MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS` | 300 | API 启动等待超时 (5min) |
| `MINERU_TASK_RESULT_DOWNLOAD_TIMEOUT_SECONDS` | 600 | 结果下载超时 (10min) |
| `MINERU_PDF_RENDER_TIMEOUT` | 300 | PDF 渲染超时 (5min) |
| `MINERU_PROCESSING_WINDOW_SIZE` | 64 | VLM 处理窗口大小 |
| `MINERU_API_ENABLE_FASTAPI_DOCS` | 1 | 是否启用 API 文档 |
| `MINERU_API_DISABLE_ACCESS_LOG` | 0 | 是否禁用访问日志 |
| `MINERU_LOG_LEVEL` | INFO | 日志级别 |
| `MINERU_DEVICE_MODE` | auto | 设备模式 (cuda/mps/cpu/npu) |
| `MINERU_VLM_FORMULA_ENABLE` | true | 是否启用公式解析 |
| `MINERU_VLM_TABLE_ENABLE` | true | 是否启用表格解析 |
| `MINERU_LMDEPLOY_DEVICE` | cuda | LMDeploy 设备类型 |
| `MINERU_LOCAL_API_LAUNCH_MODE` | subprocess | API 启动模式 |

---

## 9. 总结

MinerU 的任务队列实现是一个轻量级的内存队列方案：

**优点**:
- 简单高效，适合单机部署
- 并发控制使用 Semaphore，代码简洁
- 支持直接调用 `aio_do_parse`，非常适合 MCP Server 集成
- 自动清理过期任务

**缺点**:
- 内存存储，重启丢失
- 缺少任务超时取消机制
- 缺少日期分层存储
- 缺少优先级队列

**MCP Server 集成建议**:
1. 直接调用 `aio_do_parse` 而不通过 HTTP
2. 使用 SQLite 持久化任务状态
3. 增加任务超时取消机制
4. 可选增加日期分层存储
5. 复用 MinerU 的 Semaphore 并发控制模式