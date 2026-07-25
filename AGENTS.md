# AGENTS.md

本文件面向 AI 编码代理，介绍本仓库的架构、命令与约定。项目注释与文档主要使用中文，本文保持一致。

## 项目概述

本项目（mineru-server，仓库：`https://github.com/ErixWong/mineru-server`）是一个面向远程调用和 MCP 客户端的 MinerU PDF 解析服务。基于上游 [MinerU](https://github.com/opendatalab/MinerU)（当前固定 tag `mineru-3.4.4-released`），将四类能力整合到一个服务中：

- **REST API**：提交任务、轮询状态、列出交付物（deliverables）、按 `download_key` 下载结果
- **MCP Tools**：6 个工具（`create_task`、`get_task_status`、`list_deliverables`、`download_deliverable`、`cancel_task` 为主工具；`list_tasks` 为辅助工具）
- **Admin Console**：前后端一体化管理台（登录、调用方 caller 管理、任务查看、后处理规则、设置）
- **本地任务队列**：SQLite 持久化、并发控制、取消与超时处理

所有解析任务都是异步的：提交后返回 `task_id`，轮询状态，完成后再读取交付物。

## 技术栈

- **后端**：Python（声明兼容 `>=3.10,<3.14`），FastAPI + Starlette + uvicorn，`mcp` SDK（Streamable HTTP / SSE / stdio），SQLite（任务队列），pydantic v2，loguru，click，bcrypt，httpx
- **上游引擎**：`mineru>=3.4.4,<4` 作为正式依赖（不再依赖运行时 `sys.path` 注入）；适配层封装在 `mineru_adapter.py`
- **Admin 前端**：Vue 3 + TypeScript + Vite + Pinia + vue-router + Bootstrap 5 + markdown-it/dompurify（独立 SPA，目录 `admin-ui`）
- **部署**：Docker 多阶段单镜像（前端 build 阶段 + Python 运行时），docker-compose，GitHub Actions 发布 slim 镜像到 GHCR

## 仓库结构

```text
├── pyproject.toml              # Python package metadata, dependencies, pytest config
├── src/mineru_mcp/             # Service source code, see module map below
├── admin-ui/                   # Admin Console SPA (Vue 3 + Vite)
├── tests/                      # Python tests plus local integration samples
├── docs/                       # Project docs (design/, deployment/, mineru/, tasks/)
├── output/                     # Local runtime output (tasks.db, parse output), do not commit business data
├── Dockerfile                  # All-in-One full image (mineru[vlm,pipeline,vllm], about 12-16 GB)
├── Dockerfile.slim             # Slim image (mineru[pipeline], about 7-9 GB, used by CI)
├── docker-compose.yml          # Two-service template: vLLM server + mineru-mcp
└── .env.example                # Environment variable example
```

### `src/mineru_mcp/` 模块划分

| 模块 | 职责 |
|------|------|
| `cli.py` | CLI 入口（`mineru-mcp`），stdio / http 两种模式，加载 `.env` |
| `app.py` | 统一 Starlette 应用：挂载 REST API、MCP、Admin SPA 静态文件、`AuthMiddleware`（Bearer token） |
| `api.py` | REST API 路由（`/api/tasks`、`/api/backends` 等） |
| `server.py` | MCP Server 定义与 tool 注册 |
| `admin_api.py` / `admin_auth.py` / `admin_console.py` | Admin Console 后端：session cookie + CSRF 鉴权、caller 管理、SPA 托管 |
| `auth.py` / `principal.py` | Bearer token 鉴权、当前调用方（principal）解析与上下文 |
| `config.py` | 全部环境变量读取（`MCPConfig.from_env()`），含后端白名单 `VALID_BACKENDS` |
| `mineru_adapter.py` | 上游 MinerU 适配层（唯一与 mineru 引擎对接的封装） |
| `mineru_worker.py` | 解析任务执行体 |
| `postprocess.py` | 解析后处理（标题优化等，依赖 LLM 配置） |
| `task_queue/` | `database.py`（SQLite）、`scheduler.py`、`processor.py`、`state_service.py`、`file_manager.py` |
| `services/task_service.py` | 任务服务层 |
| `models.py` / `errors.py` / `validation.py` / `concurrency.py` / `utils.py` | 数据模型、错误码、入参校验、并发原语、工具函数 |

### `admin-ui/src/` 结构

`views/`（LoginPage、Dashboard、Tasks、TaskDetail、Callers、PostprocessRules、Settings、ChangePassword）、`stores/auth.ts`、`router.ts`、`layouts/`、`lib/`。前端 `base` 为 `/admin/`，Vite 开发服务器端口 `5180`，`/api` 代理到 `127.0.0.1:8002`。

## 构建与运行命令

### 本地后端（明确使用 Python 3.13）

仓库已验证可正常拉起本地 MinerU `pipeline` 依赖的是 Python 3.13 环境；机器上有多套 Python 时不要依赖默认 `python`。

```bash
py -3.13 -m pip install -e .          # 安装（含 mineru 依赖）

py -3.13 -m mineru_mcp.cli                              # stdio 模式
py -3.13 -m mineru_mcp.cli --mode http --port 8002      # HTTP 模式（API + MCP）
py -3.13 -m mineru_mcp.cli --mode http --port 8002 --no-mcp   # 仅 REST API
```

### Admin 前端开发

```bash
cd admin-ui
npm install
npm run dev        # 开发服务器 http://127.0.0.1:5180/admin/login
npm run build      # vue-tsc 类型检查 + vite build → dist/
```

### Docker

```bash
cp .env.example .env
docker compose build && docker compose up -d
curl http://localhost:8002/health
# 管理台 http://localhost:8002/admin/login；API 文档 http://localhost:8002/api/docs
```

Dockerfile 为前后端一体化单镜像：构建阶段跑 `npm run build`，最终镜像只启动一个 Python 进程，单端口 `8002` 同时提供 `/admin/*`（SPA）、`/api/*`、`/mcp/*`。镜像内 Python 为 3.11（`python:3.11-slim-bookworm`）。

## 测试策略

Python 测试位于 `tests/`，pytest 配置在 `pyproject.toml`（`testpaths = ["tests"]`，`asyncio_mode = "auto"`）：

```bash
py -3.13 -m pip install -e ".[test]"
py -3.13 -m pytest
```

- 大部分是单元/契约测试：`test_mcp.py`、`test_mcp_tool_names.py`、`test_output_contract.py`、`test_upload_submit_api.py`、`test_admin_security.py`、`test_authorization.py`、`test_image_routes.py`、`test_postprocess*.py`、`test_mineru_dependency_contract.py` 等，使用 FastAPI `TestClient`，不需要真实模型。
- `tests/manual/mcp_integration.py` 是**联调脚本**（用 `python` 直接运行而非 pytest）：需要先启动服务（`python -m mineru_mcp.app` 或 CLI http 模式），并通过环境变量 `MINERU_TEST_CALLER_API_KEY` 注入真实 caller API key。
- 仓库根 `tests/` 下是手工联调材料：`test_async_service.js` 与真实样本 PDF（如 `奇瑞质量协议签章版-1-2.pdf`，用于图文混编联调）。
- 前端无测试框架，质量门禁是 `npm run build` 中的 `vue-tsc --noEmit` 类型检查。

## 鉴权模型（重要，两套刻意分开，不要混用）

- **公开 API / MCP**：`Authorization: Bearer <caller_api_key>`。caller 及其 api_key 通过 Admin Console 创建并存入 SQLite；由 `app.py` 的 `AuthMiddleware` 统一校验。`/health`、`/api/health`、`/admin*`、OPTIONS 预检豁免。
- **Admin Console（`/api/admin/*`）**：session cookie + CSRF token，外加 same-origin 校验（`MINERU_ADMIN_SAME_ORIGIN_CHECK`）。`/mcp` 到 `/mcp/` 的等价由中间件内部改写实现，避免 307 重定向丢失 Authorization 头导致 401。

## 解析后端

`config.py` 的 `VALID_BACKENDS`：`pipeline`（本地流水线，无 VLM）、`vlm-http-client`、`hybrid-http-client`（本地 OCR + 远程 VLM，**当前默认推荐**）、`vlm-auto-engine`、`hybrid-auto-engine`（本地 VLM，需 GPU）。`*-http-client` 依赖 `MINERU_VL_SERVER` / `MINERU_VL_API_KEY` / `MINERU_VL_MODEL_NAME` 指向 OpenAI 兼容服务（compose 模板中为同 compose 内的 vLLM 容器，端口 30000）。未配置外部 VLM 时，真实 PDF 联调优先用 `pipeline`。

## 输出契约

产物写入 `MINERU_OUTPUT_ROOT`（默认 `output/`），结构为 `output/YYYY/MM/DD/{task_id}/`，后端输出子目录映射：`vlm-http-client → vlm`、`pipeline → auto`、`hybrid-http-client → hybrid_auto`。

- 必需产物：`md`、`middle_json`
- 推荐产物：`content_list`、`content_list_v2`（v2 上游标注为 development version，不作为稳定公开契约核心字段）
- 可选产物：`model_json`（默认生成，调试用）

图片已纳入统一 deliverables 模型，主读取路径是 `list_deliverables` → `download_deliverable`。对外主路径见根 `README.md` 的接口表；项目未上线前不保留旧结果读取兼容层，以主路径为准。

## 关键环境变量

完整清单见 `.env.example`。最常用：

- `MCP_SERVER_MODE` / `MCP_HTTP_PORT`（默认 http / 8002）
- `MINERU_DEFAULT_BACKEND`（默认 `hybrid-http-client`）
- `MINERU_OUTPUT_ROOT` / `MINERU_DB_PATH`（默认 `output` / `output/tasks.db`）
- `MINERU_MAX_CONCURRENT` / `MINERU_TASK_TIMEOUT` / `MINERU_RETRY_LIMIT` / `MINERU_CLEANUP_DAYS`
- `MINERU_VL_SERVER` / `MINERU_VL_API_KEY` / `MINERU_VL_MODEL_NAME`（http-client 后端需要）
- `MINERU_POSTPROCESS_CONTEXT_SIZE`（后处理分片原文预算，字符数非 tokens，下限 4096，应显著低于模型上下文窗口）

## CI 与部署

- `.github/workflows/docker-publish.yml`：推送 `main`/`master` 或 `v*` 标签时，用 `Dockerfile.slim` 构建并推送 `ghcr.io/erixwong/mineru-server:latest-slim`；PR 仅构建不推送。
- `docker-compose.yml` 默认面向 remote VLM 模式：`vlm-server`（`vllm/vllm-openai:v0.21.0`，GPU，端口 30000）+ `mineru-mcp`（依赖 vlm-server healthy）。切到本地引擎后端时需同步移除/忽略 vlm-server 与 `depends_on`。
- 镜像变体：`Dockerfile` 完整版（含 vllm 本地推理，约 12–16 GB）vs `Dockerfile.slim`（仅 pipeline + http-client 后端，约 7–9 GB）。
- 部署文档见 `docs/deployment/`（含 Strix Halo / AMD ROCm 方案）。

## 开发约定与注意事项

- 代码与文档注释以**中文**为主，新代码请保持同样风格。
- 部分源码文件（如 `app.py`、`docker-compose.yml`）使用 CRLF 行尾，编辑时注意保持原有行尾风格。
- MCP tool 命名已按资源和动作收敛（`create_task` / `get_task_status` / …），新增 tool 遵循同一风格。
- `docs/archive/mcp-server/TODO.md` 与 `docs/archive/mcp-server/research_notes.md` 为历史材料，不作为当前接口契约依据；接口契约以根 `README.md` 与 `docs/README.md` 为准。
- `mineru` 是正式依赖；与上游引擎的交互只通过 `mineru_adapter.py` 适配层，不要在其他模块直接耦合 mineru 内部 API。

## 安全注意事项

- Admin Console 初始密码由 `MINERU_ADMIN_INITIAL_PASSWORD` 设置；**未设置时默认回退 `admin123`，生产环境必须显式覆盖**。
- 反向代理场景：`MINERU_ADMIN_TRUST_PROXY_HEADERS` 仅在确认代理会覆盖客户端同名头时开启；`MINERU_ADMIN_ALLOWED_ORIGINS` 配置浏览器实际访问的外部 Origin。
- `MINERU_CORS_ORIGINS` 仅对公开 OCR API 生效，Admin 页面与 Admin API 始终由 same-origin + CSRF 保护。
- `.env`、数据库 `output/tasks.db`（含 caller api_key、密码哈希）属敏感数据，不要提交或外泄；`bcrypt` 用于密码哈希。
- `MCP_MAX_UPLOAD_SIZE` 控制上传体积（默认 500MB）。
