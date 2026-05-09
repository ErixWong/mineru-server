# MinerU MCP Server

MinerU PDF 解析能力的 MCP (Model Context Protocol) 服务端实现。

## 版本

当前版本: `0.1.3`

## 功能概述

将 MinerU 的 PDF 解析能力通过 MCP 协议暴露给 MCP 客户端（如 Claude Desktop、Cline 等）。

### 支持的 MCP 工具

| 工具 | 功能 |
|------|------|
| `parse_pdf` | 同步解析 PDF，返回 Markdown 内容 |
| `submit_task` | 提交异步解析任务，返回任务 ID |
| `get_task_status` | 查询任务状态 |
| `get_task_result` | 获取任务结果 |
| `extract_markdown` | 提取 Markdown 内容 |
| `get_images` | 获取提取的图片（Base64） |
| `list_backends` | 列出支持的解析后端 |
| `health_check` | 检查 MinerU API 健康状态 |

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

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINERU_API_BASE` | `http://localhost:8000` | MinerU FastAPI 地址 |
| `MINERU_DEFAULT_BACKEND` | `hybrid-http-client` | 默认解析后端 |
| `MINERU_VLM_BASE_URL` | - | VLM API 基础 URL（如 https://api.openai.com/v1） |
| `MINERU_VLM_API_KEY` | - | VLM API 密钥 |
| `MINERU_VLM_MODEL` | - | VLM 模型名称（如 gpt-4o） |
| `MINERU_TITLE_BASE_URL` | - | 标题优化 LLM API 基础 URL（可选） |
| `MINERU_TITLE_API_KEY` | - | 标题优化 LLM API 密钥（可选） |
| `MINERU_TITLE_MODEL` | - | 标题优化 LLM 模型名称（可选） |
| `MCP_SERVER_NAME` | `MinerU MCP Server` | MCP Server 名称 |
| `MCP_SERVER_MODE` | `stdio` | 服务模式 (stdio/http) |
| `MCP_HTTP_HOST` | `0.0.0.0` | HTTP 服务主机 |
| `MCP_HTTP_PORT` | `8001` | HTTP 服务端口 |
| `MCP_HTTP_AUTH_TOKEN` | - | HTTP 认证 Token（可选） |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |
| `MCP_ALLOWED_DIRS` | `/app/input,/app/data` | 允许的文件目录 |
| `MCP_ALLOW_SYMLINKS` | `false` | 是否允许符号链接 |
| `MCP_MAX_REQUESTS_PER_MINUTE` | `60` | 每分钟最大请求数 |
| `MCP_MAX_CONCURRENT_TASKS` | `5` | 最大并发任务数 |
| `MCP_TASK_TIMEOUT_SECONDS` | `600` | 任务超时时间（秒） |

### 配置参数传递流程

MCP Server 启动时，会自动将 `.env` 中的 VLM 和 Title 配置同步到 MinerU 配置文件 `~/.mineru/mineru.json`，确保配置只需设置一次。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         配置参数传递流程                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  .env 文件                    MCP Server                    MinerU 后端      │
│  ─────────                    ──────────                    ──────────       │
│                                                                             │
│  MINERU_API_BASE         ──→  config.py                    MinerU FastAPI    │
│                                 │                                          │
│                                 ↓                                          │
│                           mineru_client.py                                  │
│                                 │                                          │
│                                 ↓                                          │
│                           HTTP POST /file_parse                            │
│                                 │                                          │
│                                 ↓                                          │
│                           base_url 参数                                    │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  MINERU_DEFAULT_BACKEND  ──→  config.py                    MinerU FastAPI    │
│                                 │                                          │
│                                 ↓                                          │
│                           server.py                                         │
│                           (parse_pdf/submit_task)                           │
│                                 │                                          │
│                                 ↓                                          │
│                           HTTP POST /file_parse                            │
│                                 │                                          │
│                                 ↓                                          │
│                           backend 参数                                      │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  MINERU_VLM_BASE_URL     ──→  config.py                    MinerU FastAPI    │
│                                 │                                          │
│                                 ↓                                          │
│                           server.py                                         │
│                           (parse_pdf/submit_task)                           │
│                                 │                                          │
│                                 ↓                                          │
│                           HTTP POST /file_parse                            │
│                                 │                                          │
│                                 ↓                                          │
│                           server_url 参数                                   │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  MINERU_VLM_API_KEY      ──→  config.py                    ~/.mineru/       │
│  MINERU_VLM_MODEL             │                             mineru.json      │
│                                 │                                          │
│                                 ↓                                          │
│                           sync_to_mineru_config()                          │
│                                 │                                          │
│                                 ↓                                          │
│                           写入 llm-aided-config.vlm                         │
│                                 │                                          │
│                                 ↓                                          │
│                           MinerU 启动时读取                                  │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  MINERU_TITLE_API_KEY    ──→  config.py                    ~/.mineru/       │
│  MINERU_TITLE_BASE_URL        │                             mineru.json      │
│  MINERU_TITLE_MODEL            │                                          │
│                                 ↓                                          │
│                           sync_to_mineru_config()                          │
│                                 │                                          │
│                                 ↓                                          │
│                           写入 llm-aided-config.title_aided                 │
│                                 │                                          │
│                                 ↓                                          │
│                           MinerU 启动时读取                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**关键说明：**

1. **`MINERU_VLM_BASE_URL`** → 作为 `server_url` 参数传递给 MinerU FastAPI
   - MinerU FastAPI 接受此参数用于 http-client 后端
   - 见 [`fast_api.py:798-803`](../cli/fast_api.py:798)

2. **`MINERU_VLM_API_KEY` 和 `MINERU_VLM_MODEL`** → 自动同步到 `~/.mineru/mineru.json`
   - MinerU FastAPI 不接受 API Key 和 Model 作为请求参数
   - 必须通过配置文件传递给 MinerU 后端
   - MCP Server 启动时自动同步，无需手动配置

3. **`MINERU_DEFAULT_BACKEND`** → 作为默认 `backend` 参数
   - 如果 MCP 工具调用时未指定 `backend`，使用此默认值

**自动同步的配置文件示例：**

```json
// ~/.mineru/mineru.json (由 MCP Server 自动生成)
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
src/mineru/mcp/
├── __init__.py          # 模块导出
├── config.py            # 配置管理
├── validation.py        # 输入验证
├── errors.py            # 错误处理
├── auth.py              # 认证模块
├── concurrency.py       # 并发控制
├── mineru_client.py     # MinerU HTTP 客户端
├── server.py            # MCP Server 实现
├── cli.py               # CLI 入口
├── entrypoint.py        # All-in-One 容器启动
└── tests/
    ├── __init__.py
    └── test_mcp.py      # 单元测试
```

## 安全特性

### 输入验证 (`validation.py`)

- 路径遍历攻击防护
- 文件类型白名单验证
- 文件大小限制（500 MB）
- 符号链接检查
- 目录限制

```python
from mineru.mcp import validate_file_path, ValidationError

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
from mineru.mcp import MCPError, from_exception

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
from mineru.mcp import get_concurrency_manager

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
status = await client.get_task_status(task_id)
result = await client.wait_for_task(task_id)
```

### HTTP 调用

```bash
# 健康检查
curl http://localhost:8001/mcp/tools/health_check

# 解析 PDF
curl -X POST http://localhost:8001/mcp/tools/parse_pdf \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/app/input/document.pdf"}'
```

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