# Python Package Notes

`mineru-mcp` is the Python package in this repository. It contains the backend runtime for MinerU Server:

- `mineru-mcp` CLI entry point
- REST API under `/api`
- MCP Streamable HTTP endpoint under `/mcp/`
- Admin API used by the Vue Admin Console
- SQLite-backed task queue
- MinerU adapter and worker integration

This is a package-level note. For project-level usage, deployment, public API paths, MCP tool names, and authentication, use the root [README.md](../README.md).

## Package Layout

```text
mineru-server/
+-- pyproject.toml
+-- src/mineru_mcp/
    +-- api.py                 # Public REST API
    +-- admin_api.py           # Admin Console API
    +-- app.py                 # Unified Starlette app
    +-- auth.py                # Bearer caller key auth
    +-- cli.py                 # CLI entry point
    +-- config.py              # Environment configuration
    +-- mineru_adapter.py      # MinerU integration boundary
    +-- mineru_worker.py       # Task execution body
    +-- server.py              # MCP tool registration
    +-- task_queue/            # Database, scheduler, state, file manager
+-- tests/
```

## Install

The package declares Python `>=3.10,<3.14`. Local development on this repository has been validated with Python 3.13.

```powershell
py -3.13 -m pip install -e ".[test]"
```

## Run

```powershell
# stdio mode
py -3.13 -m mineru_mcp.cli

# HTTP mode: REST + MCP + Admin SPA
py -3.13 -m mineru_mcp.cli --mode http --port 8002

# HTTP mode: REST/Admin only
py -3.13 -m mineru_mcp.cli --mode http --port 8002 --no-mcp
```

The CLI loads `.env` only from the current working directory. Start it from the repository root when using the example `.env`.

## Important Boundaries

- Only `mineru_adapter.py` should couple directly to upstream MinerU APIs.
- Public REST/MCP authentication uses caller API keys from the database.
- Admin Console authentication uses session cookies and CSRF tokens.
- `MINERU_CALLER_KEY_MASTER_KEY` is required for caller API key encryption.

---

# Python 包说明

`mineru-mcp` 是本仓库中的 Python 包，承载 MinerU Server 的后端运行时：

- `mineru-mcp` CLI 入口
- `/api` 下的 REST API
- `/mcp/` 下的 MCP Streamable HTTP 端点
- Vue 管理台使用的 Admin API
- SQLite 持久化任务队列
- MinerU 适配层与 worker 集成

本文是包级说明。项目级使用方式、部署、公开 API 路径、MCP tool 名称和鉴权模型，请以根目录 [README.md](../README.md) 为准。

## 包结构

```text
mineru-server/
+-- pyproject.toml
+-- src/mineru_mcp/
    +-- api.py                 # 公开 REST API
    +-- admin_api.py           # Admin Console API
    +-- app.py                 # 统一 Starlette 应用
    +-- auth.py                # Bearer caller key 鉴权
    +-- cli.py                 # CLI 入口
    +-- config.py              # 环境配置
    +-- mineru_adapter.py      # MinerU 集成边界
    +-- mineru_worker.py       # 任务执行体
    +-- server.py              # MCP tool 注册
    +-- task_queue/            # 数据库、调度器、状态服务、文件管理
+-- tests/
```

## 安装

包声明兼容 Python `>=3.10,<3.14`。本仓库当前本地开发已验证 Python 3.13。

```powershell
py -3.13 -m pip install -e ".[test]"
```

## 运行

```powershell
# stdio 模式
py -3.13 -m mineru_mcp.cli

# HTTP 模式：REST + MCP + Admin SPA
py -3.13 -m mineru_mcp.cli --mode http --port 8002

# HTTP 模式：仅 REST/Admin
py -3.13 -m mineru_mcp.cli --mode http --port 8002 --no-mcp
```

CLI 只会从当前工作目录读取 `.env`。使用示例 `.env` 时，请从仓库根目录启动。

## 重要边界

- 只有 `mineru_adapter.py` 应直接耦合上游 MinerU API。
- 公开 REST/MCP 鉴权使用数据库中的 caller API key。
- Admin Console 鉴权使用 session cookie 和 CSRF token。
- `MINERU_CALLER_KEY_MASTER_KEY` 是 caller API key 加密所需配置。
