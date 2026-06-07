# MinerU MCP Server

MinerU PDF 解析能力的 MCP (Model Context Protocol) 服务端实现。

## 版本

当前版本: `0.2.0`

## 功能概述

将 MinerU 的 PDF 解析能力通过 MCP 协议暴露给 MCP 客户端（如 Claude Desktop、Cline 等）。

**新特性（v0.2.0）**：
- SQLite 任务队列（持久化存储）
- 并发控制（asyncio.Semaphore）
- 超时自动取消
- Bearer Token 认证（可选）
- REST API 端点（任务提交、查询）

### 支持的 MCP 工具

| 工具 | 功能 |
|------|------|
| `submit_task` | 提交异步解析任务，返回任务 ID |
| `get_task` | 查询任务状态和结果 |
| `get_images` | 获取提取的图片（Base64） |
| `list_backends` | 列出支持的解析后端 |
| `health_check` | 检查服务健康状态 |

**注意**: 所有解析任务均为异步模式，避免长耗时任务导致超时。

## 运行模式

### 1. stdio 模式（桌面客户端）

适用于 Claude Desktop、Cline 等 MCP 客户端：

```bash
mineru-mcp
```

### 2. HTTP 模式（远程调用）

适用于远程 HTTP 调用：

```bash
mineru-mcp --mode http --port 8001
```

## 安装

```bash
cd src
pip install -e .
```

安装后可使用 `mineru-mcp` 命令。

## 配置

### 环境变量

#### MCP Server 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_SERVER_NAME` | `MinerU MCP Server` | MCP Server 名称 |
| `MCP_SERVER_MODE` | `stdio` | 服务模式 (stdio/http) |
| `MCP_HTTP_HOST` | `0.0.0.0` | HTTP 服务主机 |
| `MCP_HTTP_PORT` | `8001` | HTTP 服务端口 |
| `MCP_HTTP_AUTH_TOKEN` | - | HTTP 认证 Token（可选） |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |

#### MinerU 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINERU_DEFAULT_BACKEND` | `hybrid-http-client` | 默认解析后端 |
| `MINERU_VLM_BASE_URL` | - | VLM API 基础 URL（如 https://api.openai.com/v1） |
| `MINERU_VLM_API_KEY` | - | VLM API 密钥 |
| `MINERU_VLM_MODEL` | - | VLM 模型名称（如 gpt-4o） |
| `MINERU_TITLE_BASE_URL` | - | 标题优化 LLM API 基础 URL（可选） |
| `MINERU_TITLE_API_KEY` | - | 标题优化 LLM API 密钥（可选） |
| `MINERU_TITLE_MODEL` | - | 标题优化 LLM 模型名称（可选） |

#### 任务队列配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINERU_MAX_CONCURRENT` | `3` | 最大并发处理数 |
| `MINERU_TASK_TIMEOUT` | `3600` | 任务超时时间（秒） |
| `MINERU_RETRY_LIMIT` | `3` | 最大重试次数 |
| `MINERU_CLEANUP_DAYS` | `30` | 清理多少天前的已完成任务 |
| `MINERU_DB_PATH` | `/app/output/tasks.db` | SQLite 数据库路径 |

#### 其他配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_ALLOWED_DIRS` | `/app/input,/app/data` | 允许的文件目录 |
| `MCP_ALLOW_SYMLINKS` | `false` | 是否允许符号链接 |
| `MCP_MAX_UPLOAD_SIZE` | `500MB` | 最大上传文件大小（支持 KB/MB/GB） |
| `MCP_MAX_REQUESTS_PER_MINUTE` | `60` | 每分钟最大请求数 |
| `MCP_MAX_CONCURRENT_TASKS` | `5` | 最大并发任务数 |
| `MCP_TASK_TIMEOUT_SECONDS` | `600` | 任务超时时间（秒） |

### 配置参数传递流程

### 配置说明

MCP Server 直接调用 MinerU 核心函数（`aio_do_parse`），VLM 配置通过 MinerU 配置文件传递。

**关键配置项**：

1. **`MINERU_VLM_BASE_URL`** → VLM API 地址
   - 用于 http-client 后端（如 `hybrid-http-client`）

2. **`MINERU_VLM_API_KEY` 和 `MINERU_VLM_MODEL`** → 写入 `~/.mineru/mineru.json`
   - MinerU 启动时自动读取

3. **`MINERU_DEFAULT_BACKEND`** → 默认解析后端
   - 如果调用时未指定 `backend`，使用此默认值

**自动同步的配置文件示例**：

```json
// ~/.mineru/mineru.json (由 MinerU 自动生成)
{
    "llm-aided-config": {
        "vlm": {
            "api_key": "sk-your-api-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o"
        },
        "title_aided": {
            "enable": true,
            "api_key": "sk-your-api-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini"
        }
    },
    "config_version": "1.3.1"
}
```

### 生成认证 Token

```bash
python -m mineru.mcp.auth
# 输出: Generated auth token: xxx...
# 设置: MCP_HTTP_AUTH_TOKEN=xxx...
```

## 模块结构

```
src/mineru_mcp/
├── __init__.py          # 模块导出
├── config.py            # 配置管理
├── validation.py        # 输入验证
├── errors.py            # 错误处理
├── auth.py              # 认证模块
├── concurrency.py       # 并发控制
├── api.py               # REST API
├── app.py               # Unified app, mounts /api and /mcp
├── models.py            # Response models
├── server.py            # MCP Server 实现
├── cli.py               # CLI 入口
└── task_queue/          # Queue scheduler, processor, state service
```

## 安全特性

### 输入验证 (`validation.py`)

- 路径遍历攻击防护
- 文件类型白名单验证
- 文件大小限制（500 MB）
- 符号链接检查
- 目录限制

```python
from mineru_mcp import validate_file_path, ValidationError

try:
    validated_path = validate_file_path(
        "/app/input/document.pdf",
        allowed_dirs=[Path("/app/input")],
    )
except ValidationError as e:
    print(f"Error: {e.code} - {e.message}")
```

### 结构化错误 (`errors.py`)

统一的错误码和自动脱敏：

```python
from mineru_mcp import MCPError, from_exception

# 预定义错误
error = file_not_found("/path/to/file.pdf")
print(error.to_dict())
# {"status": "error", "error_code": "FILE_NOT_FOUND", ...}

# 异常转换（自动脱敏敏感信息）
try:
    ...
except Exception as e:
    error = from_exception(e)
```

### Bearer Token 认证 (`auth.py`)

HTTP 模式可选认证：

```bash
# 设置 Token
export MCP_HTTP_AUTH_TOKEN=your-secret-token

# 客户端调用
curl -H "Authorization: Bearer your-secret-token" http://localhost:8001/mcp
```

### 并发控制 (`concurrency.py`)

限流和并发任务管理：

```python
from mineru_mcp import get_concurrency_manager

manager = get_concurrency_manager()

# 检查限流
if await manager.check_rate_limit():
    # 获取任务槽位
    if await manager.acquire_task_slot("task-123"):
        try:
            result = await parse_pdf(...)
        finally:
            await manager.release_task_slot("task-123")

# 获取状态
status = manager.get_status()
# {"rate_limit": {"current_rate": 5, "max_per_minute": 60},
#  "tasks": {"active_count": 2, "max_concurrent": 5}}
```

## 解析后端

| 后端 | 说明 | 语言支持 |
|------|------|----------|
| `pipeline` | 传统流水线（无 VLM） | 多语言 |
| `vlm-auto-engine` | 本地 VLM 引擎 | 中/英 |
| `vlm-http-client` | 远程 VLM（OpenAI API） | 中/英 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 多语言 |
| `hybrid-http-client` | 本地 OCR + 远程 VLM（推荐） | 多语言 |

## 解析参数说明

### 内容识别参数

MCP 工具和 REST API 支持以下内容识别参数：

| 参数 | 默认值 | 功能 |
|------|--------|------|
| `formula_enable` | `true` | 公式识别 - 将数学公式转为 LaTeX 格式嵌入 Markdown |
| `table_enable` | `true` | 表格识别 - 将表格转为 Markdown 表格结构 |
| `image_analysis` | `true` | 图像分析 - VLM 对图片内容生成 AI 描述（需 VLM 后端） |

**输出效果示例**：

```
Markdown 文件内容（document.md）：
─────────────────────────────────
## 第1页

这里是一段文字...

![图1](images/image_001.jpg)
*图1描述：该图展示了系统架构，包含前端、后端和数据库三个模块*

继续文字内容...

$$E = mc^2$$   ← LaTeX 公式（formula_enable=true）

| 列1 | 列2 | 列3 |   ← Markdown 表格（table_enable=true）
|-----|-----|-----|
| A   | B   | C   |
```

**参数效果对比**：

| image_analysis | VLM 后端效果 | Pipeline 后端效果 |
|----------------|--------------|-------------------|
| `true` | Markdown 中有图片 AI 描述 + 图片引用路径 | 仅 OCR 图片中的文字（如有） |
| `false` | Markdown 中仅引用图片路径 `![](images/xxx.jpg)` | 仅引用图片路径 |

### 输出目录结构

```
output/2026/05/10/{task_id}/
├── input.pdf                     # 上传的原始文件
└── document/vlm/                 # MinerU 输出目录
    ├── document.md               # Markdown 内容（图片描述混编其中）
    ├── document_middle.json      # 中间处理结果
    ├── document_content_list.json # 结构化内容列表
    └── images/                   # 提取的图片
        ├── image_001.jpg
        └── image_002.png
```

**说明**：
- `{task_id}` = UUID 任务标识
- `document` = 从输入文件名提取（去掉扩展名）
- `vlm` = 后端类型目录（vlm/pipeline/hybrid_vlm 等）
- 图片描述直接嵌入 `.md` 文件，原图保存到 `images/` 目录

## Docker 部署

### All-in-One 容器

```bash
# 构建镜像
cd src/docker
docker build -f mineru-mcp.Dockerfile -t mineru-mcp:latest .

# 运行容器
docker run -d \
  -p 8000:8000 -p 8001:8001 \
  -e MCP_SERVER_MODE=http \
  -e MCP_HTTP_AUTH_TOKEN=your-token \
  -v /path/to/input:/app/input \
  mineru-mcp:latest
```

### Docker Compose

```bash
docker-compose -f mineru-mcp-compose.yml up -d
```

## 测试

```bash
cd src
pytest mineru/mcp/tests/test_mcp.py -v
```

## Claude Desktop 配置

在 Claude Desktop 配置文件中添加：

```json
{
  "mcpServers": {
    "mineru": {
      "command": "mineru-mcp",
      "env": {
        "MINERU_API_BASE": "http://localhost:8000"
      }
    }
  }
}
```

## API 使用示例

### REST API（NEW）

**任务队列模式的 REST API 端点**：

```bash
# 健康检查（无需认证）
curl http://localhost:8001/api/health

# 任务队列统计（需认证）
curl -H "Authorization: Bearer your-token" \
  http://localhost:8001/api/stats

# 提交任务（异步）
curl -X POST http://localhost:8001/api/tasks \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.pdf" \
  -F "backend=hybrid-http-client"

# 先上传文件，再通过 upload_id 提交任务（大文件推荐路径）
curl -X POST http://localhost:8001/api/uploads \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.pdf"

curl -X POST http://localhost:8001/api/tasks/from-upload \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "upl_123456",
    "backend": "hybrid-http-client",
    "lang": "ch"
  }'

# 查询任务状态
curl -H "Authorization: Bearer your-token" \
  http://localhost:8001/api/tasks/{task_id}

# 获取任务结果（Markdown 内容）
curl -H "Authorization: Bearer your-token" \
  http://localhost:8001/api/tasks/{task_id}/result

# 获取提取的图片
curl -H "Authorization: Bearer your-token" \
  http://localhost:8001/api/tasks/{task_id}/images

# 取消任务
curl -X DELETE -H "Authorization: Bearer your-token" \
  http://localhost:8001/api/tasks/{task_id}
```

### REST 状态接口兼容说明

`GET /api/tasks/{task_id}` 当前同时承担两类用途：

- 状态轮询接口
- 兼容旧客户端的结果读取接口

兼容规则如下：

- 默认情况下，`GET /api/tasks/{task_id}` 会在任务 `completed` 时返回 `markdown`
- 若调用方只需要状态元信息，可显式传入 `?return_md=false`
- 新调用方仍建议在完成态使用 `GET /api/tasks/{task_id}/result` 获取正文内容

这样处理的目的是在保留新接口语义的同时，不破坏历史轮询客户端。

### REST 状态返回矩阵

| 接口 | 状态 | 关键字段 | 说明 |
|------|------|----------|------|
| `GET /api/tasks/{task_id}` | `pending` | `task_id`, `status`, `progress`, `message`, `created_at`, `updated_at`, `started_at=null`, `completed_at=null` | 任务已创建，尚未开始执行 |
| `GET /api/tasks/{task_id}` | `processing` | `task_id`, `status`, `progress`, `message`, `created_at`, `updated_at`, `started_at` | 任务正在处理 |
| `GET /api/tasks/{task_id}` | `completed` | `task_id`, `status`, `progress=100`, `message`, `created_at`, `updated_at`, `started_at`, `completed_at`, `markdown` | 兼容旧调用方时默认返回 `markdown` |
| `GET /api/tasks/{task_id}` | `failed` | `task_id`, `status`, `progress=-1`, `message`, `created_at`, `updated_at`, `started_at`, `completed_at`, `error` | 失败原因通过 `error` 返回 |
| `GET /api/tasks/{task_id}` | `cancelled` | `task_id`, `status`, `progress=-1`, `message`, `created_at`, `updated_at`, `started_at`, `completed_at`, `error` | `error` / `message` 保留真实取消原因 |
| `GET /api/tasks/{task_id}` | `404` | `status=error`, `error=TASK_NOT_FOUND`, `message` | 任务不存在 |
| `GET /api/tasks/{task_id}/result` | `completed` | `task_id`, `status`, `markdown` | 推荐的新结果读取接口 |
| `GET /api/tasks/{task_id}/result` | `400` | `status=error`, `error=TASK_NOT_COMPLETED`, `message` | 任务未完成时不返回正文 |
| `GET /api/tasks/{task_id}/images` | `completed` | `task_id`, `status`, `images`, `count` | 返回提取图片 |
| `GET /api/tasks/{task_id}/images` | `pending/processing/failed/cancelled` | `task_id`, `status`, `images={}`, `count=0` | 不抛错，返回空结果 |
| `DELETE /api/tasks/{task_id}` | 非终态 | `task_id`, `cancelled=true`, `message` | 任务成功取消 |
| `DELETE /api/tasks/{task_id}` | 已终态 | `task_id`, `cancelled=false`, `message` | 已完成、失败或取消的任务不可再次取消 |
| `POST /api/uploads` | `uploaded` | `upload_id`, `status`, `file_name`, `mime_type`, `size_bytes`, `sha256`, `created_at` | 上传文件并返回 `upload_id` |
| `POST /api/tasks/from-upload` | `submitted` | `task_id`, `message`, `created_at` | 基于 `upload_id` 创建正式解析任务 |

### MCP 状态返回矩阵

| 工具 | 状态 | 关键字段 | 说明 |
|------|------|----------|------|
| `get_task` | `pending` / `processing` | `task_id`, `status`, `progress`, `message`, `created_at`, `updated_at` | MCP 侧轮询状态 |
| `get_task` | `completed` | `task_id`, `status`, `created_at`, `completed_at`, `result` | `result` 为 Markdown 正文 |
| `get_task` | `failed` | `task_id`, `status`, `message`, `updated_at`, `error` | 返回真实失败原因 |
| `get_task` | `cancelled` | `task_id`, `status`, `message`, `updated_at`, `error` | 返回真实取消原因，可区分人工取消与超时 |
| `get_task` | `not_found` | `task_id`, `status=not_found`, `error` | 任务不存在 |
| `get_images` | `completed` | `task_id`, `status`, `images`, `count` | 返回提取图片 |
| `get_images` | 非完成态 | `task_id`, `status`, `message`, `images={}`, `count=0` | 任务未完成时返回空图片结果 |

### 字段语义

- `message`：当前状态的人类可读说明，适合展示与日志对齐
- `error`：终态错误原因，仅在失败、取消或异常情况下使用
- `progress`：任务进度，`0-100` 为处理中进度，`-1` 表示失败或取消
- `started_at`：任务首次进入 `processing` 的时间，只应写入一次
- `updated_at`：最近一次状态或进度更新时间
- `completed_at`：任务进入终态的时间

### Python 客户端

```python
from mineru.mcp import MinerUClient, create_mcp_server

# 直接使用 MinerU 客户端
client = MinerUClient("http://localhost:8000")

# 同步解析
result = await client.parse_pdf_sync(
    file_path="/app/input/document.pdf",
    backend="hybrid-http-client",
    lang="ch",
)

# 异步任务
task_id = await client.submit_task(...)
status = await client.get_task(task_id)
result = await client.wait_for_task(task_id)
```

### HTTP 调用

MCP HTTP 模式使用的是 **Streamable HTTP JSON-RPC** 通道，入口为：

- `POST http://localhost:8001/mcp`

当前工具调用不应再使用旧的 `/mcp/tools/...` 示例路径。

推荐做法：

- 使用 MCP 官方 SDK 连接 `http://localhost:8001/mcp`
- 或使用项目内的 `tests/test_async_service.js --test-mcp` 做 MCP 通道验证

MCP 可用工具包括：

- `submit_task`
- `submit_uploaded_task`
- `get_task`
- `get_images`
- `cancel_task`
- `list_tasks`
- `list_backends`
- `get_supported_formats`

### 大文件上传策略

当前 MCP `submit_task` 工具仍保留 `file_base64` 输入方式，原因是：

- 兼容当前实现
- 兼容只支持文本参数的 MCP 客户端
- 适合作为小文件或兜底路径

但对于较大的 PDF、图片或其他二进制文件，`file_base64` 存在明显缺点：

- 体积会比原始文件膨胀约 33%
- 客户端和服务端都需要经历一次额外的编码/解码与内存复制
- 对远程 `streamable-http` 场景不够高效

因此，推荐的演进方向是：

- 保留 `submit_task(file_base64, file_name, ...)` 作为兼容路径
- 为大文件引入 `upload session + submit by upload_id` 方案，避免把整个二进制直接内联到 MCP tool 参数中

### 当前大文件路径（已实现）

当前已经实现了一套阶段性 `upload_id` 方案，作为 `file_base64` 之外的更高效文件提交流程：

#### 第一步：上传文件并获取 `upload_id`

通过 REST 端点上传文件：

```bash
curl -X POST http://localhost:8001/api/uploads \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.pdf"
```

返回：

```json
{
  "upload_id": "upl_123456",
  "status": "uploaded",
  "file_name": "document.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 31457280,
  "sha256": "a1b2c3d4...",
  "created_at": "2026-06-07T11:00:00Z"
}
```

#### 第二步：通过 `upload_id` 提交任务

**REST 方式**：

```bash
curl -X POST http://localhost:8001/api/tasks/from-upload \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "upl_123456",
    "backend": "hybrid-http-client",
    "lang": "ch"
  }'
```

**MCP 方式**：

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "method": "tools/call",
  "params": {
    "name": "submit_uploaded_task",
    "arguments": {
      "upload_id": "upl_123456",
      "backend": "hybrid-http-client",
      "lang": "ch"
    }
  }
}
```

返回：

```json
{
  "task_id": "task_abcdef",
  "message": "Task submitted successfully",
  "created_at": "2026-06-07T11:05:00Z"
}
```

#### 第三步：后续流程保持不变

任务提交后，后续仍使用现有工具：

- `get_task`
- `get_images`
- `cancel_task`

**说明**：这是当前的阶段性实现，它已经可以避免在 MCP tool 参数里传输整块 base64，但仍把整个文件一次性读入内存。因此它适合小到中等大小的文件，比 `file_base64` 更高效，但还不算完整的大文件流式上传方案。

### 后续目标路径（尚未实现）

后续计划将当前 `upload_id` 方案演进为更完善的 `upload session` 模型：

1. MCP 工具 `create_upload_session`：创建会话并返回独立 `upload_url`
2. 客户端通过该 `upload_url` 做分块上传或断点续传
3. MCP 工具 `complete_upload`：确认上传完成
4. MCP 工具 `submit_uploaded_task`：基于完成的上传创建任务

### 是否需要断点续传

不一定。

`upload session + submit by upload_id` 的第一版可以先不做断点续传，只做：

- 创建会话
- 单次完整上传
- 上传完成后再提交任务

这样已经能显著改善大文件场景下的效率问题。

如果后续确实存在超大文件、弱网、长时间上传等场景，再继续演进为：

- 分块上传
- 查询已上传块
- 续传与完成确认

## 错误码

| 类别 | 错误码 | HTTP 状态 |
|------|--------|-----------|
| 文件 | `FILE_NOT_FOUND` | 404 |
| 文件 | `PATH_TRAVERSAL` | 403 |
| 文件 | `FILE_TOO_LARGE` | 413 |
| 文件 | `INVALID_EXTENSION` | 400 |
| 任务 | `TASK_NOT_FOUND` | 404 |
| 任务 | `TASK_FAILED` | 500 |
| 任务 | `TASK_TIMEOUT` | 504 |
| 任务 | `TASK_STILL_PROCESSING` | 202 |
| 验证 | `INVALID_BACKEND` | 400 |
| 验证 | `INVALID_PAGE_RANGE` | 400 |
| API | `MINERU_API_ERROR` | 502 |
| API | `MINERU_API_UNAVAILABLE` | 503 |
| 认证 | `AUTH_MISSING` | 401 |
| 认证 | `AUTH_INVALID` | 401 |

## 更新日志

### v0.2.0 (2026-05-10)
- **任务队列系统**（SQLite 持久化）
  - 直接调用 MinerU 核心函数（无 HTTP 开销）
  - 并发控制（asyncio.Semaphore）
  - 超时自动取消
  - 容器重启恢复
- **认证集成**
  - Bearer Token 认证（可选启用）
  - AuthMiddleware（统一保护所有端点）
- **REST API**
  - 任务提交、状态查询端点
- **文件管理**
  - 日期分层目录（output/YYYY/MM/DD/{uuid}/）
  - 文件类型验证
- **测试覆盖**
  - task_queue_basic 测试
  - auth_integration 测试
  - api_integration 测试

### v0.1.3 (2026-04-12)
- 添加并发控制模块 (`concurrency.py`)
- Rate limiting（滑动窗口算法）
- Concurrent task limiter（信号量）
- 超时任务自动清理

### v0.1.2 (2026-04-11)
- 添加 Bearer Token 认证 (`auth.py`)
- 时序安全 Token 验证

### v0.1.1 (2026-04-11)
- 添加输入验证 (`validation.py`)
- 添加结构化错误 (`errors.py`)
- 自动脱敏敏感信息

### v0.1.0 (2026-04-11)
- 初始实现
- 8 个 MCP 工具
- stdio 和 HTTP 模式
- MinerU HTTP 客户端

---

*MinerU MCP Server - 将 PDF 解析能力暴露给 AI 客户端*
