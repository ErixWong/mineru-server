# MinerU MCP Server (Python)

一个基于 Python 的 Model Context Protocol (MCP) 服务器，与 MinerU 一体化部署在同一个容器中。

## 项目概述

本项目实现了一个 MCP 服务器，将 MinerU 的 PDF 解析能力通过 MCP 协议暴露给支持 MCP 的客户端（如 Claude Desktop、Cline 等）。

**核心优势**：
- **一体化部署**：MinerU + MCP 服务器在同一容器中，简化部署
- **零配置连接**：MCP 服务器直接调用本地 MinerU API，无需额外配置
- **两种运行模式**：支持 stdio（桌面客户端）和 HTTP（远程调用）模式

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                       All-in-One 容器                        │
│  ┌─────────────────────┐    ┌──────────────────────────┐    │
│  │   MinerU 解析核心   │    │    MCP Server (Python)   │    │
│  │   (进程内直接调用)  │    │    stdio / HTTP 模式     │    │
│  │                     │    │  - create_task           │    │
│  │  - 原生解析能力     │    │  - get_task_status       │    │
│  │  - aio_do_parse     │    │  - list_deliverables     │    │
│  │  - 底层任务处理     │    │  - download_deliverable  │    │
│  │                     │    │  - cancel_task           │    │
│  │                     │    │  - list_tasks            │    │
│  └─────────────────────┘    └──────────────────────────┘    │
│      同进程挂载 /api 与 /mcp（统一 Starlette 应用，端口 8002）│
└─────────────────────────────────────────────────────────────┘
```

## 文档处理流程

```mermaid
flowchart TB
    subgraph Client["MCP 客户端"]
        A1["用户/LLM 请求"]
        A2["接收结果"]
    end

    subgraph MCP["MCP Server (端口 8002)"]
        B1["create_task 工具"]
        B2["get_task_status 工具"]
        B3["list_deliverables 工具"]
        B4["download_deliverable 工具"]
    end

    subgraph MinerU["MinerU FastAPI (端口 8002)"]
        C1["原生 MinerU 解析能力"]
        C2["/api/tasks 异步提交"]
        C3["/api/tasks/{id} 状态查询"]
        C4["/api/tasks/{id}/deliverables 交付物列表"]
    end

    subgraph Storage["存储层"]
        D1["上传目录<br>/output/{task_id}/uploads"]
        D2["解析结果目录<br>/output/{task_id}/{pdf_name}/"]
        D3["Markdown 文件<br>{pdf_name}.md"]
        D4["图片目录<br>images/*.jpg"]
    end

    %% 上传流程
    A1 -->|"1. 调用 create_task"| B1
    B1 -->|"2. 提交异步任务"| C2
    
    %% 文件存储
    C2 -->|"3. 保存上传文件"| D1

    %% 异步处理流程
    C2 -->|"4. 返回 task_id"| B1
    B1 -->|"5. 返回 task_id"| A2
    
    %% 状态查询
    A2 -->|"6. 查询状态<br>get_task_status"| B2
    B2 -->|"7. GET /api/tasks/{id}"| C3
    C3 -->|"8. 返回状态<br>pending/processing/completed"| B2
    B2 -->|"9. 返回状态"| A2

    %% 获取交付物列表
    A2 -->|"10. 状态=completed<br>调用 list_deliverables"| B3
    B3 -->|"11. GET /api/tasks/{id}/deliverables"| C4
    C4 -->|"12. 返回交付物列表"| B3
    B3 -->|"13. 返回交付物列表"| A2

    %% 下载单个交付物
    A2 -->|"14. 下载交付物<br>download_deliverable"| B4
    B4 -->|"15. GET /api/tasks/{id}/deliverables/download?download_key=..."| C4
    C4 -->|"16. 返回内容"| B4
    B4 -->|"17. 返回内容"| A2
```

### 流程说明

#### 异步模式（`/api/tasks`）

1. **提交任务**：调用 `create_task` 或 `POST /api/tasks`，返回 `task_id`
2. **轮询状态**：使用 `get_task_status` 查询处理进度
3. **获取交付物列表**：状态变为 `completed` 后，调用 `list_deliverables` 或 `GET /api/tasks/{id}/deliverables` 获取可下载文件列表
4. **下载交付物**：调用 `download_deliverable` 或 `GET /api/tasks/{id}/deliverables/download?download_key=...` 下载具体文件

#### 当前结果获取方式

- 状态接口：`GET /api/tasks/{id}`
- 交付物列表接口：`GET /api/tasks/{id}/deliverables`
- 单个交付物下载：`GET /api/tasks/{id}/deliverables/download?download_key=...`

当前项目文档不再以 ZIP 返回作为主说明，交付和联调应以 REST JSON 响应与 MCP 工具返回为准。

## 功能特性

- **PDF 解析**：支持解析 PDF 文档，提取文本、图片、表格和公式
- **MCP 协议支持**：完全兼容 Model Context Protocol 标准
- **多种后端支持**：
  - `pipeline`：传统管道模式
  - `vlm-http-client`：远程 VLM 解析
  - `hybrid-http-client`：混合模式（本地 OCR + 远程 VLM）
  - `vlm-auto-engine`：本地 VLM 自动引擎
  - `hybrid-auto-engine`：本地混合管道
- **多语言支持**：中文、英文、日文、韩文等
- **公式识别**：支持数学公式识别
- **表格识别**：支持表格结构识别

## 快速开始

### 环境要求

- Docker（推荐）或 Python 3.10+
- MinerU 服务（一体化部署时已包含）

### 使用 Docker（推荐）

```bash
# 构建一体化镜像
docker build -t mineru-mcp-all-in-one:latest .

# 启动容器（stdio 模式）
docker run -d \
  --name mineru-mcp \
  -v $(pwd)/input:/input \
  -v $(pwd)/output:/output \
  --device /dev/kfd:/dev/kfd \
  --device /dev/dri:/dev/dri \
  -e MINERU_VL_SERVER=http://your-vlm-server:8000/v1 \
  -e MINERU_VL_API_KEY=your-api-key \
  -e MINERU_VL_MODEL_NAME=your-model \
  mineru-mcp-all-in-one:latest

# 启动容器（HTTP 模式）
docker run -d \
  --name mineru-mcp \
  -p 8002:8002 \
  -e MCP_SERVER_MODE=http \
  mineru-mcp-all-in-one:latest

# 认证：使用数据库 caller API key 模式
# 请通过 admin console (http://localhost:8002/admin) 创建 caller
# 发起请求时设置 Header: Authorization: Bearer <caller_api_key>
```

### 本地开发

```bash
cd mcp-server
pip install -e .

# stdio 模式
mineru-mcp --mode stdio

# HTTP 模式
mineru-mcp --mode http --port 8002
```

## MCP 工具列表

### MCP Tool 清单

#### 1. `create_task`

基于文件内容创建异步解析任务，或基于已上传文件的 upload_id 创建任务。

**参数**：
- `file_base64` (string, required for file upload): 文件 Base64 内容
- `upload_id` (string, required for uploaded file): 已上传文件的 ID
- `file_name` (string, optional): 文件名
- `backend` (string, optional): 解析后端
- `lang` (string, optional): 文档语言
- `formula_enable` (boolean, optional): 启用公式识别
- `table_enable` (boolean, optional): 启用表格识别
- `image_analysis` (boolean, optional): 启用图片分析

#### 2. `get_task_status`

查询解析任务状态，返回 pending/processing/completed/failed/cancelled。

#### 3. `list_deliverables`

列出已完成任务的所有可下载交付物。

#### 4. `download_deliverable`

下载单个交付物（支持 Markdown、JSON、图片等）。

#### 5. `cancel_task`

取消未完成的任务。

#### 6. `list_tasks`

列出任务，可按状态过滤。

## 与 MCP 客户端集成

### HTTP 模式调用

当前项目的 MCP HTTP 模式使用 **Streamable HTTP JSON-RPC**，并使用数据库 caller API key 认证。

正确入口为：

- `POST /mcp`

建议做法：

- 使用 MCP 官方 SDK 建立连接并调用工具
- 或使用仓库内的 `tests/test_async_service.js --test-mcp` 进行脚本化验证

## 项目结构

```
mineru/
  ├── mcp-server/                 # MCP 服务器代码
  │  ├──  src/mineru_mcp/         # Python 包
  │  │  ├──  api.py              # REST API
  │  │  ├──  app.py              # Unified app, mounts /api and /mcp
  │  │  ├──  server.py           # MCP tools
  │  │  ├──  models.py           # Response models
  │  │  ├──  task_queue/         # Queue scheduler, processor, state service
  │  │  ├──  pyproject.toml
  │  ├──  docs/                  # 文档
  │  ├──  tests/
  │  ├──  .env.example
```

## 技术栈

**复用 MinerU 已有依赖**：
- `httpx` - HTTP 客户端（MinerU 已有）
- `loguru` - 日志系统（MinerU 已有）
- `click` - CLI 入口点（MinerU 已有）
- `fastapi` / `uvicorn` - HTTP 模式（MinerU 已有，可选）

**额外添加**：
- `mcp` - MCP Python SDK（官方）
- **配置管理**: `pydantic-settings`

## 开发指南

### 本地开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式化
black src/mineru_mcp/

# 类型检查
mypy src/mineru_mcp/
```

### 构建一体化镜像

```bash
docker build -t mineru-mcp-all-in-one:latest .
```

## 环境变量

### MCP Server 配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MCP_SERVER_MODE` | 运行模式 | `stdio` |
| `MCP_HTTP_PORT` | HTTP 端口 | `8002` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

### 认证说明

MCP Server 使用数据库 caller API key 认证模式。请通过 admin console (http://localhost:8002/admin) 创建 caller，并在请求时设置 Header：`Authorization: Bearer <caller_api_key>`

### MinerU 配置（用于 VLM 后端）

| 变量名 | 说明 |
|--------|------|
| `MINERU_VL_SERVER` | VLM API 地址（如 OpenAI、阿里云） |
| `MINERU_VL_API_KEY` | VLM API 密钥 |
| `MINERU_VL_MODEL_NAME` | VLM 模型名称 |

**架构说明**：
- MCP Server 直接调用 MinerU 核心函数（`aio_do_parse`）
- VLM 配置通过 MinerU 配置文件 (`~/.mineru/mineru.json`) 传入

## 相关链接

- [MinerU 官方文档](https://mineru.readthedocs.io/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## 许可证

MIT License

✌Bazinga！