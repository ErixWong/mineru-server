# MinerU Server

[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-ready-green.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

MinerU Server exposes [MinerU](https://github.com/opendatalab/MinerU) PDF parsing as a remote service for REST clients, MCP clients, and an integrated Admin Console.

The service is asynchronous: upload a PDF, receive a `task_id`, poll task status, then list and download deliverables such as Markdown, JSON outputs, and extracted images.

## What It Provides

- REST API for task submission, status polling, deliverable listing, downloads, cancellation, and manual post-processing runs.
- MCP tools for agent clients: `create_task`, `get_task_status`, `list_deliverables`, `download_deliverable`, `cancel_task`, `list_tasks`, and post-processing helpers.
- Admin Console at `/admin/*` for login, caller API key management, task inspection, task cloning, failed-task copy/retry workflows, post-processing plans, and runtime diagnostics.
- Local SQLite-backed task queue with persistence, concurrency control, cancellation, timeout handling, ownership checks, and artifact management.
- Multiple MinerU backends, including local pipeline mode and OpenAI-compatible remote VLM modes.

## Repository Layout

```text
mineru-server/
+-- pyproject.toml              # Python package metadata and pytest config
+-- src/mineru_mcp/             # REST API, MCP server, Admin API, queue, MinerU adapter
+-- admin-ui/                   # Vue 3 Admin Console SPA
+-- tests/                      # Python tests and manual integration scripts
+-- docs/                       # Design notes, deployment docs, task plans, archive docs
+-- scripts/                    # Maintenance scripts
+-- Dockerfile                  # Full image: MinerU with vlm/pipeline/vllm extras
+-- Dockerfile.slim             # Slim image: MinerU pipeline + http-client backends
+-- docker-compose.yml          # Remote-VLM deployment template
+-- .env.example                # Local development environment example
```

The current source tree is flattened at the repository root. There is no package layer that needs to be entered before running backend, frontend, or tests.

## Quick Start

### 1. Local Python Backend

Use Python 3.13 explicitly on Windows when several Python versions are installed.

```powershell
py -3.13 -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Set `MINERU_CALLER_KEY_MASTER_KEY` in `.env` before starting. It must be a Fernet-compatible key: URL-safe base64 that decodes to exactly 32 bytes.

```powershell
py -3.13 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Start the unified HTTP service from the repository root:

```powershell
py -3.13 -m mineru_mcp.cli --mode http --port 8002
```

Useful URLs:

- Admin Console: `http://127.0.0.1:8002/admin/login`
- REST docs: `http://127.0.0.1:8002/api/docs`
- Health check: `http://127.0.0.1:8002/health`
- MCP endpoint: `http://127.0.0.1:8002/mcp/`

For REST-only local debugging:

```powershell
py -3.13 -m mineru_mcp.cli --mode http --port 8002 --no-mcp
```

### 2. Admin UI Development

Run the backend first, then start the Vite dev server:

```powershell
cd admin-ui
npm install
npm run dev
```

The dev UI runs at `http://127.0.0.1:5180/admin/login` and proxies `/api` to `127.0.0.1:8002`.

Build the production SPA:

```powershell
cd admin-ui
npm run build
```

### 3. Docker Compose

`docker-compose.yml` is a remote-VLM template. It starts:

- `vlm-server`: an OpenAI-compatible vLLM service on port `30000`.
- `mineru-mcp`: the MinerU Server process on port `8002`.

Inject secrets from the host environment or an external env file. The Docker image build does not read `.env`.

```bash
export MINERU_CALLER_KEY_MASTER_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
docker compose up -d
curl http://localhost:8002/health
```

The compose template defaults to `hybrid-http-client`, so `mineru-mcp` depends on the `vlm-server` health check. If you switch to `pipeline`, remove or ignore the VLM service dependency in your deployment.

### 4. Use the GHCR Docker Image

GitHub Actions automatically builds the slim Docker image from `Dockerfile.slim` and publishes it to GitHub Container Registry (`ghcr.io`) when changes are pushed to `main` / `master`, when `v*` tags are pushed, or when the workflow is run manually.

The slim image is published in two torch flavors:

| Tag | Torch flavor | Size | Use when |
| --- | --- | --- | --- |
| `latest-slim-cuda` | CUDA | ~7-9 GB | The host has an NVIDIA GPU; local OCR stages (hybrid/pipeline backends) can use it |
| `latest-slim-cpu` | CPU only | ~4.5-6 GB | No GPU on the host, or image size matters more than OCR speed |

`latest-slim` remains as an alias of `latest-slim-cuda` for backward compatibility.

Pull the latest slim image (CUDA flavor shown):

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda
```

Start the service from the published image:

```bash
export MINERU_CALLER_KEY_MASTER_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
docker run --rm -p 8002:8002 \
  -e MINERU_CALLER_KEY_MASTER_KEY="$MINERU_CALLER_KEY_MASTER_KEY" \
  -e MCP_SERVER_MODE=http \
  -e MINERU_DEFAULT_BACKEND=pipeline \
  -v "$(pwd)/output:/app/output" \
  ghcr.io/erixwong/mineru-server:latest-slim-cuda
```

For Compose deployments, replace the local build with the published image:

```yaml
services:
  mineru-mcp:
    image: ${MINERU_IMAGE:-ghcr.io/erixwong/mineru-server:latest-slim-cuda}
```

The bundled `docker-compose.yml` uses this GHCR image by default. Set `MINERU_IMAGE`
to override it for local or private image tags.

More details about generated tags and cleanup policy are in [docs/deployment/github-packages.md](docs/deployment/github-packages.md).

### 5. Manual Docker Build

Full image:

```bash
docker build -t mineru-server:full -f Dockerfile .
```

Slim image:

```bash
docker build -t mineru-server:slim -f Dockerfile.slim .
```

Run an image:

```bash
docker run --rm -p 8002:8002 \
  -e MINERU_CALLER_KEY_MASTER_KEY="$MINERU_CALLER_KEY_MASTER_KEY" \
  -e MCP_SERVER_MODE=http \
  mineru-server:slim
```

## Authentication

There are two intentionally separate authentication models.

Public REST API and MCP:

- Use `Authorization: Bearer <caller_api_key>`.
- Caller API keys are created and managed in the Admin Console.
- Caller keys are encrypted in SQLite using `MINERU_CALLER_KEY_MASTER_KEY`.
- Keep the same master key for the same `MINERU_DB_PATH`; changing it can make existing caller keys impossible to reveal or authenticate.

Admin Console:

- Uses session cookies, CSRF tokens, and same-origin checks.
- Initial password comes from `MINERU_ADMIN_INITIAL_PASSWORD`.
- If unset, the current fallback is `admin123`; always override it in production.

## REST API

Public API routes are mounted under `/api`. The simplified root health check is also available at `/health`.
Task list and queue statistics are scoped to the current caller API key.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Lightweight service health check |
| `GET` | `/api/health` | Full health check with queue stats |
| `GET` | `/api/stats` | Queue statistics |
| `GET` | `/api/backends` | Supported parsing backends |
| `POST` | `/api/tasks` | Upload a PDF and create an async task |
| `GET` | `/api/tasks?page=1&size=20` | List recent tasks visible to the current caller |
| `GET` | `/api/tasks/{task_id}` | Query task status and optionally return Markdown |
| `GET` | `/api/tasks/{task_id}/deliverables` | List task deliverables |
| `GET` | `/api/tasks/{task_id}/deliverables/download?download_key=...` | Download one deliverable |
| `GET` | `/api/tasks/{task_id}/deliverables/images/{image_name}` | Serve an extracted image |
| `DELETE` | `/api/tasks/{task_id}` | Cancel a task |
| `GET` | `/api/postprocess-plans` | List enabled post-processing plans |
| `POST` | `/api/tasks/{task_id}/postprocess-runs` | Start a manual post-processing run |
| `GET` | `/api/tasks/{task_id}/postprocess-runs` | List post-processing runs for a task |
| `POST` | `/api/postprocess-runs/{run_id}/cancel` | Cancel a post-processing run |

Create a task:

```bash
curl -X POST http://localhost:8002/api/tasks \
  -H "Authorization: Bearer <caller_api_key>" \
  -F "file=@document.pdf" \
  -F "backend=hybrid-http-client" \
  -F "lang=ch"
```

Poll status:

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>?return_md=false"
```

List recent tasks:

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks?page=1&size=20&status=completed"
```

List deliverables:

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>/deliverables"
```

Download one deliverable:

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>/deliverables/download?download_key=<download_key>"
```

## MCP Tools

HTTP MCP endpoint:

```text
POST /mcp/
```

Available tools:

| Tool | Purpose |
| --- | --- |
| `create_task` | Create an async parsing task from base64 PDF content |
| `get_task_status` | Poll task status |
| `list_deliverables` | List logical artifacts for a completed task |
| `download_deliverable` | Download one artifact by `download_key` |
| `cancel_task` | Cancel a pending or processing task |
| `list_tasks` | List recent tasks visible to the current caller |
| `list_postprocess_rules` | Compatibility name for listing enabled post-processing plans |
| `run_postprocess` | Trigger a manual post-processing run on a completed task |
| `list_postprocess_runs` | List post-processing runs and step status for a task |

Example MCP call:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_task",
    "arguments": {
      "file_base64": "<base64-pdf>",
      "file_name": "document.pdf",
      "backend": "hybrid-http-client",
      "lang": "ch"
    }
  }
}
```

## Parsing Backends

| Backend | Description | GPU requirement |
| --- | --- | --- |
| `hybrid-http-client` | Local OCR plus remote OpenAI-compatible VLM; default and recommended for remote VLM deployments | No GPU for `mineru-mcp` |
| `vlm-http-client` | Remote OpenAI-compatible VLM | No GPU for `mineru-mcp` |
| `pipeline` | Traditional local pipeline without VLM | No GPU required |
| `vlm-auto-engine` | Local VLM engine | GPU/runtime dependent |
| `hybrid-auto-engine` | Local OCR plus local VLM engine | GPU/runtime dependent |

When no external VLM service is configured, use `pipeline` for real PDF debugging.

## Deliverables

Outputs are written under `MINERU_OUTPUT_ROOT`, defaulting to `output/`.

Typical layout:

```text
output/YYYY/MM/DD/{task_id}/
+-- input.pdf
+-- input/{backend_output_dir}/
    +-- input.md
    +-- input_middle.json
    +-- input_model.json
    +-- input_content_list.json
    +-- input_content_list_v2.json
    +-- images/
        +-- image_001.jpg
        +-- image_002.png
```

Backend output directory mapping:

- `pipeline` -> `auto`
- `vlm-http-client` -> `vlm`
- `hybrid-http-client` -> `hybrid_auto`

Deliverable contract:

- Required: `md`, `middle_json`
- Recommended: `content_list`, `content_list_v2`
- Optional/debug: `model_json`
- Images are part of the unified deliverables model and should be accessed through `list_deliverables` and `download_deliverable`.

> **Duplicate submission behavior**: tasks with the same file content (sha256) and identical parsing parameters are parsed only once; subsequent duplicate tasks reuse the parse artifacts and complete in seconds. Duplicates are transparent to callers — their lifecycle and deliverables behave exactly like normal tasks.

## Post-Processing

Post-processing is managed as plans and runs:

- Plans define one or more actions.
- Runs are created automatically during task creation when enabled, or manually with the REST API, MCP tools, or Admin Console.
- Each run stores step-level status and can be cancelled.
- LLM-backed actions use `MINERU_TITLE_BASE_URL`, `MINERU_TITLE_API_KEY`, and `MINERU_TITLE_MODEL`.
- `MINERU_POSTPROCESS_CONTEXT_SIZE` controls the per-chunk source text budget in characters, not tokens. The minimum enforced value is `4096`.

## Key Configuration

Common environment variables:

```bash
MCP_SERVER_MODE=http
MCP_HTTP_HOST=0.0.0.0
MCP_HTTP_PORT=8002
MCP_LOG_LEVEL=INFO

MINERU_CALLER_KEY_MASTER_KEY=replace-with-fernet-key
MINERU_DEFAULT_BACKEND=hybrid-http-client
MINERU_OUTPUT_ROOT=output
MINERU_DB_PATH=output/tasks.db
MINERU_MAX_CONCURRENT=3
MINERU_TASK_TIMEOUT=3600
MINERU_RETRY_LIMIT=3
MINERU_CLEANUP_DAYS=300

MINERU_VL_SERVER=http://localhost:30000/v1
MINERU_VL_API_KEY=
MINERU_VL_MODEL_NAME=MinerU2.5-Pro-2605-1.2B
MINERU_VLM_MAX_CONCURRENCY=2

MINERU_ADMIN_INITIAL_PASSWORD=change-this-password
MINERU_ADMIN_SAME_ORIGIN_CHECK=true
MINERU_ADMIN_TRUST_PROXY_HEADERS=false
MINERU_ADMIN_ALLOWED_ORIGINS=http://127.0.0.1:5180,http://localhost:5180
MINERU_CORS_ORIGINS=*
```

`MINERU_RETRY_LIMIT` requeues failed processing attempts until the configured
retry budget is exhausted. `MINERU_CLEANUP_DAYS` controls periodic cleanup of terminal
tasks and their output directories.

Local CLI startup loads `.env` only from the current working directory. Start commands in this README assume the repository root as the working directory.

## Testing

Backend tests:

```powershell
py -3.13 -m pip install -e ".[test]"
py -3.13 -m pytest
```

Frontend type check and build:

```powershell
cd admin-ui
npm run build
```

Manual MCP integration script:

```powershell
py -3.13 tests/manual/mcp_integration.py
```

The manual script expects a running HTTP service and a real caller API key in `MINERU_TEST_CALLER_API_KEY`.

## License

MIT License

## Acknowledgements

- [MinerU](https://github.com/opendatalab/MinerU)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

# MinerU Server 中文说明

MinerU Server 将 [MinerU](https://github.com/opendatalab/MinerU) PDF 解析能力封装成一个可远程调用的服务，同时面向 REST 客户端、MCP 客户端和内置管理台。

服务采用异步任务模型：上传 PDF 后返回 `task_id`，调用方轮询任务状态，完成后再列出并下载 Markdown、JSON、图片等交付物。

## 当前能力

- REST API：任务提交、状态轮询、交付物列表、交付物下载、任务取消、手动后处理。
- MCP Tools：提供 `create_task`、`get_task_status`、`list_deliverables`、`download_deliverable`、`cancel_task`、`list_tasks` 以及后处理相关工具。
- Admin Console：位于 `/admin/*`，支持登录、caller API key 管理、任务查看、任务复制、失败任务复制后重试、后处理方案、运行时诊断等。
- 本地任务队列：SQLite 持久化、并发控制、取消、超时、所有权校验和产物管理。
- 多种 MinerU 后端：支持本地 pipeline，也支持 OpenAI 兼容远程 VLM 模式。

## 仓库结构

```text
mineru-server/
+-- pyproject.toml              # Python 包元数据与 pytest 配置
+-- src/mineru_mcp/             # REST API、MCP、Admin API、任务队列、MinerU 适配层
+-- admin-ui/                   # Vue 3 管理台 SPA
+-- tests/                      # Python 测试与手工联调脚本
+-- docs/                       # 设计、部署、任务计划、历史归档文档
+-- scripts/                    # 维护脚本
+-- Dockerfile                  # 完整镜像：MinerU vlm/pipeline/vllm extras
+-- Dockerfile.slim             # 精简镜像：pipeline + http-client 后端
+-- docker-compose.yml          # remote VLM 部署模板
+-- .env.example                # 本地开发环境变量示例
```

当前源码已经拉平到仓库根目录。启动后端、前端和测试时都不需要再进入额外的包目录。

## 快速开始

### 1. 本地 Python 后端

Windows 上如果安装了多个 Python 版本，建议显式使用 Python 3.13。

```powershell
py -3.13 -m pip install -e ".[test]"
Copy-Item .env.example .env
```

启动前需要在 `.env` 中设置 `MINERU_CALLER_KEY_MASTER_KEY`。它必须是 Fernet 兼容密钥：URL-safe base64，解码后正好 32 字节。

```powershell
py -3.13 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

从仓库根目录启动统一 HTTP 服务：

```powershell
py -3.13 -m mineru_mcp.cli --mode http --port 8002
```

常用地址：

- 管理台：`http://127.0.0.1:8002/admin/login`
- REST 文档：`http://127.0.0.1:8002/api/docs`
- 健康检查：`http://127.0.0.1:8002/health`
- MCP 端点：`http://127.0.0.1:8002/mcp/`

仅调试 REST API 时：

```powershell
py -3.13 -m mineru_mcp.cli --mode http --port 8002 --no-mcp
```

### 2. Admin UI 开发

先启动后端，再启动 Vite：

```powershell
cd admin-ui
npm install
npm run dev
```

开发页面是 `http://127.0.0.1:5180/admin/login`，`/api` 会代理到 `127.0.0.1:8002`。

构建生产版 SPA：

```powershell
cd admin-ui
npm run build
```

### 3. Docker Compose

`docker-compose.yml` 是 remote VLM 模式模板，会启动两个服务：

- `vlm-server`：OpenAI 兼容 vLLM 服务，端口 `30000`。
- `mineru-mcp`：MinerU Server 服务进程，端口 `8002`。

敏感配置应从宿主机环境变量或外部 env file 注入。Docker 镜像构建不会读取 `.env`。

```bash
export MINERU_CALLER_KEY_MASTER_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
docker compose up -d
curl http://localhost:8002/health
```

Compose 默认使用 `hybrid-http-client`，因此 `mineru-mcp` 默认依赖 `vlm-server` 的健康检查。如果切换到 `pipeline`，部署时应移除或忽略 VLM 服务依赖。

### 4. 使用 GHCR Docker 镜像

GitHub Actions 会基于 `Dockerfile.slim` 自动构建精简 Docker 镜像，并在推送到 `main` / `master`、推送 `v*` 标签，或手动运行 workflow 时发布到 GitHub Container Registry (`ghcr.io`)。

slim 镜像分两种 torch flavor 发布：

| 标签 | torch flavor | 体积 | 适用场景 |
| --- | --- | --- | --- |
| `latest-slim-cuda` | CUDA | 约 7-9 GB | 主机有 NVIDIA GPU，本地 OCR 阶段（hybrid/pipeline 后端）可利用 GPU 加速 |
| `latest-slim-cpu` | 仅 CPU | 约 4.5-6 GB | 主机无 GPU，或更在意镜像体积而非 OCR 速度 |

`latest-slim` 保留为 `latest-slim-cuda` 的别名，用于向后兼容。

拉取最新精简镜像（以 CUDA flavor 为例）：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda
```

使用已发布镜像启动服务：

```bash
export MINERU_CALLER_KEY_MASTER_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
docker run --rm -p 8002:8002 \
  -e MINERU_CALLER_KEY_MASTER_KEY="$MINERU_CALLER_KEY_MASTER_KEY" \
  -e MCP_SERVER_MODE=http \
  -e MINERU_DEFAULT_BACKEND=pipeline \
  -v "$(pwd)/output:/app/output" \
  ghcr.io/erixwong/mineru-server:latest-slim-cuda
```

Compose 部署时，可以把本地构建替换为已发布镜像：

```yaml
services:
  mineru-mcp:
    image: ${MINERU_IMAGE:-ghcr.io/erixwong/mineru-server:latest-slim-cuda}
```

生成的镜像标签与清理策略见 [docs/deployment/github-packages.md](docs/deployment/github-packages.md)。

### 5. 手动构建 Docker 镜像

完整镜像：

```bash
docker build -t mineru-server:full -f Dockerfile .
```

精简镜像：

```bash
docker build -t mineru-server:slim -f Dockerfile.slim .
```

运行镜像：

```bash
docker run --rm -p 8002:8002 \
  -e MINERU_CALLER_KEY_MASTER_KEY="$MINERU_CALLER_KEY_MASTER_KEY" \
  -e MCP_SERVER_MODE=http \
  mineru-server:slim
```

## 鉴权模型

项目内有两套刻意分离的鉴权模型。

公开 REST API 和 MCP：

- 使用 `Authorization: Bearer <caller_api_key>`。
- caller API key 通过管理台创建和管理。
- caller key 使用 `MINERU_CALLER_KEY_MASTER_KEY` 加密后存入 SQLite。
- 同一个 `MINERU_DB_PATH` 应保持同一个 master key；更换 master key 可能导致已有 caller key 无法 reveal 或认证。

管理台：

- 使用 session cookie、CSRF token 和 same-origin 检查。
- 初始密码来自 `MINERU_ADMIN_INITIAL_PASSWORD`。
- 未设置时当前会回退到 `admin123`；生产环境必须显式覆盖。

## REST API

公开 API 挂载在 `/api` 下。简化健康检查也可以通过 `/health` 访问。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 轻量健康检查 |
| `GET` | `/api/health` | 完整健康检查，包含队列统计 |
| `GET` | `/api/stats` | 队列统计 |
| `GET` | `/api/backends` | 支持的解析后端 |
| `POST` | `/api/tasks` | 上传 PDF 并创建异步任务 |
| `GET` | `/api/tasks?page=1&size=20` | 列出当前 caller 可见的最近任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态，可选择返回 Markdown |
| `GET` | `/api/tasks/{task_id}/deliverables` | 列出任务交付物 |
| `GET` | `/api/tasks/{task_id}/deliverables/download?download_key=...` | 下载单个交付物 |
| `GET` | `/api/tasks/{task_id}/deliverables/images/{image_name}` | 读取提取出的图片 |
| `DELETE` | `/api/tasks/{task_id}` | 取消任务 |
| `GET` | `/api/postprocess-plans` | 列出已启用的后处理方案 |
| `POST` | `/api/tasks/{task_id}/postprocess-runs` | 创建手动后处理 run |
| `GET` | `/api/tasks/{task_id}/postprocess-runs` | 查询任务的后处理 run |
| `POST` | `/api/postprocess-runs/{run_id}/cancel` | 取消后处理 run |

创建任务：

```bash
curl -X POST http://localhost:8002/api/tasks \
  -H "Authorization: Bearer <caller_api_key>" \
  -F "file=@document.pdf" \
  -F "backend=hybrid-http-client" \
  -F "lang=ch"
```

查询状态：

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>?return_md=false"
```

列出最近任务：

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks?page=1&size=20&status=completed"
```

列出交付物：

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>/deliverables"
```

下载交付物：

```bash
curl -H "Authorization: Bearer <caller_api_key>" \
  "http://localhost:8002/api/tasks/<task_id>/deliverables/download?download_key=<download_key>"
```

## MCP Tools

HTTP MCP 端点：

```text
POST /mcp/
```

当前工具：

| Tool | 用途 |
| --- | --- |
| `create_task` | 从 base64 PDF 内容创建异步解析任务 |
| `get_task_status` | 轮询任务状态 |
| `list_deliverables` | 列出已完成任务的逻辑产物 |
| `download_deliverable` | 按 `download_key` 下载单个产物 |
| `cancel_task` | 取消 pending 或 processing 状态的任务 |
| `list_tasks` | 列出当前 caller 可见的最近任务 |
| `list_postprocess_rules` | 兼容名称，用于列出已启用的后处理方案 |
| `run_postprocess` | 对已完成任务手动触发后处理 |
| `list_postprocess_runs` | 查询任务后处理 run 和步骤状态 |

MCP 调用示例：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_task",
    "arguments": {
      "file_base64": "<base64-pdf>",
      "file_name": "document.pdf",
      "backend": "hybrid-http-client",
      "lang": "ch"
    }
  }
}
```

## 解析后端

| 后端 | 说明 | GPU 要求 |
| --- | --- | --- |
| `hybrid-http-client` | 本地 OCR + OpenAI 兼容远程 VLM；remote VLM 部署下默认推荐 | `mineru-mcp` 不需要 GPU |
| `vlm-http-client` | OpenAI 兼容远程 VLM | `mineru-mcp` 不需要 GPU |
| `pipeline` | 无 VLM 的传统本地 pipeline | 不需要 GPU |
| `vlm-auto-engine` | 本地 VLM 引擎 | 取决于本地 GPU/运行时 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM 引擎 | 取决于本地 GPU/运行时 |

没有配置外部 VLM 服务时，真实 PDF 调试建议使用 `pipeline`。

## 交付物

产物默认写入 `MINERU_OUTPUT_ROOT`，默认值是 `output/`。

典型结构：

```text
output/YYYY/MM/DD/{task_id}/
+-- input.pdf
+-- input/{backend_output_dir}/
    +-- input.md
    +-- input_middle.json
    +-- input_model.json
    +-- input_content_list.json
    +-- input_content_list_v2.json
    +-- images/
        +-- image_001.jpg
        +-- image_002.png
```

后端输出目录映射：

- `pipeline` -> `auto`
- `vlm-http-client` -> `vlm`
- `hybrid-http-client` -> `hybrid_auto`

交付物契约：

- 必需：`md`、`middle_json`
- 推荐：`content_list`、`content_list_v2`
- 可选/调试：`model_json`
- 图片已经纳入统一 deliverables 模型，应通过 `list_deliverables` 和 `download_deliverable` 读取。

> **重复提交行为**：文件内容（sha256）与解析参数完全相同的任务只真实解析一次；后续重复任务复用解析产物，秒级完成。对调用方完全透明——重复任务的生命周期与交付物和普通任务表现一致。

## 后处理

后处理以 plan 和 run 的形式管理：

- plan 定义一个或多个 action。
- run 可以在任务创建时自动触发，也可以通过 REST API、MCP 工具或管理台手动触发。
- 每个 run 保存步骤级状态，并支持取消。
- LLM action 使用 `MINERU_TITLE_BASE_URL`、`MINERU_TITLE_API_KEY`、`MINERU_TITLE_MODEL`。
- `MINERU_POSTPROCESS_CONTEXT_SIZE` 控制每个分片的原文预算，单位是字符而不是 token；代码内下限是 `4096`。

## 关键配置

常用环境变量：

```bash
MCP_SERVER_MODE=http
MCP_HTTP_HOST=0.0.0.0
MCP_HTTP_PORT=8002
MCP_LOG_LEVEL=INFO

MINERU_CALLER_KEY_MASTER_KEY=replace-with-fernet-key
MINERU_DEFAULT_BACKEND=hybrid-http-client
MINERU_OUTPUT_ROOT=output
MINERU_DB_PATH=output/tasks.db
MINERU_MAX_CONCURRENT=3
MINERU_TASK_TIMEOUT=3600
MINERU_RETRY_LIMIT=3
MINERU_CLEANUP_DAYS=300

MINERU_VL_SERVER=http://localhost:30000/v1
MINERU_VL_API_KEY=
MINERU_VL_MODEL_NAME=MinerU2.5-Pro-2605-1.2B
MINERU_VLM_MAX_CONCURRENCY=2

MINERU_ADMIN_INITIAL_PASSWORD=change-this-password
MINERU_ADMIN_SAME_ORIGIN_CHECK=true
MINERU_ADMIN_TRUST_PROXY_HEADERS=false
MINERU_ADMIN_ALLOWED_ORIGINS=http://127.0.0.1:5180,http://localhost:5180
MINERU_CORS_ORIGINS=*
```

本地 CLI 启动只会从当前工作目录读取 `.env`。本文命令默认工作目录都是仓库根目录。

## 测试

后端测试：

```powershell
py -3.13 -m pip install -e ".[test]"
py -3.13 -m pytest
```

前端类型检查和构建：

```powershell
cd admin-ui
npm run build
```

手工 MCP 联调脚本：

```powershell
py -3.13 tests/manual/mcp_integration.py
```

手工脚本需要先启动 HTTP 服务，并通过 `MINERU_TEST_CALLER_API_KEY` 注入真实 caller API key。

## 许可证

MIT License

## 致谢

- [MinerU](https://github.com/opendatalab/MinerU)
- [Model Context Protocol](https://modelcontextprotocol.io/)
