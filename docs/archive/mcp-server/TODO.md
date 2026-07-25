# MinerU MCP Server - 开发任务清单 (Python 版本)

> Historical note
>
> 本文档是项目早期规划草稿，保留用于追溯设计演进。
> 其中包含的旧目录结构、旧工具名、旧 HTTP 路由和旧端口说明，**不应作为当前实现基线**。
>
> 当前实现请以以下文档为准：
> - `README.md`
> - `docs/README.md`
> - `mcp-server/README.md`

## 项目概述

基于 Python 实现 MinerU 的 MCP (Model Context Protocol) 服务器，与 MinerU 容器一体化部署。

**核心目标**：构建一个包含 MinerU + MCP 服务器的 All-in-One 容器镜像，简化部署和使用。

## 架构设计

### 一体化部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                    All-in-One 容器                         │
│  ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │   MinerU FastAPI    │    │    MCP Server (Python)   │   │
│  │   服务 (端口 8000)   │◄───│    stdio / HTTP 模式     │   │
│  │                     │    │                          │   │
│  │  - 原生 MinerU API  │    │  - submit_task          │   │
│  │  - 底层任务处理      │    │  - get_task             │   │
│  │  - 底层结果提取      │    │  - get_images           │   │
│  └─────────────────────┘    └──────────────────────────┘   │
│           ▲                           │                    │
│           │                           │                    │
│           └───────────────────────────┘                    │
│              内部 HTTP 调用 (localhost:8000)               │
└─────────────────────────────────────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
  ┌──────────────┐    ┌──────────────┐
  │  MCP 客户端   │    │  HTTP 客户端  │
  │ (Claude/Cline)│    │ (curl/代码)  │
  └──────────────┘    └──────────────┘
```

### 两种运行模式

1. **stdio 模式**（默认）
   - MCP 服务器通过标准输入输出与客户端通信
   - 适用于 Claude Desktop、Cline 等桌面客户端
   - 进程由 MCP 客户端启动和管理

2. **HTTP 模式**（可选）
   - MCP 服务器暴露 HTTP API
   - 可以被远程调用或集成到现有系统
   - 支持多客户端并发访问

## 技术栈（复用 MinerU 已有依赖）

**复用 MinerU 已有的依赖**（无需额外安装）：
- `httpx` - HTTP 客户端，调用 MinerU API
- `loguru` - 日志系统
- `click` - CLI 入口点
- `fastapi` - HTTP 模式（可选）
- `uvicorn` - HTTP 模式（可选）

**需要额外添加**：
- `mcp` - MCP Python SDK（官方）

**不需要的依赖**（MinerU 已有但 MCP Server 不需要）：
- `pydantic` / `pydantic-settings` - MinerU 未使用，MCP Server 也不需要
- `requests` - 使用 `httpx` 替代

## 开发阶段

### 第一阶段：项目初始化

- [ ] 1.1 创建项目基础结构
  - [ ] 创建 `mcp-server/` 目录结构
  - [ ] 创建 `pyproject.toml` 或 `setup.py`
  - [ ] 配置 Python 虚拟环境
  - [ ] 安装 MCP SDK: `pip install mcp`
  - [ ] 安装其他依赖: `httpx`, `pydantic`, `pydantic-settings`

- [ ] 1.2 配置开发环境
  - [ ] 创建 `.env.example` 文件
  - [ ] 配置 `.gitignore`
  - [ ] 设置 `black`/`ruff` 代码格式化
  - [ ] 配置 `mypy` 类型检查
  - [ ] 创建 `requirements.txt` 和 `requirements-dev.txt`

### 第二阶段：核心功能实现

- [ ] 2.1 MinerU API 客户端
  - [ ] 历史方案：创建独立 `mineru_client.py`
  - [ ] 使用 `httpx.AsyncClient` 封装 HTTP 调用
  - [ ] 实现 `submit_task()` - 提交 PDF 解析任务
  - [ ] 历史方案：实现 `get_task_status()` - 查询任务状态
  - [ ] 实现 `download_result()` - 下载解析结果 ZIP
  - [ ] 实现错误处理和重试机制（指数退避）
  - [ ] 添加请求/响应日志

- [ ] 2.2 MCP 服务器框架
  - [ ] 历史方案：创建 `mcp_server/server.py`
  - [ ] 使用 `mcp.server.Server` 初始化服务器
  - [ ] 配置服务器名称和版本
  - [ ] 实现工具注册装饰器
  - [ ] 配置 stdio 传输层
  - [ ] 添加服务器生命周期管理

- [ ] 2.3 配置管理
  - [ ] 历史方案：创建 `mcp_server/config.py`
  - [ ] 使用 `pydantic-settings` 管理配置
  - [ ] 支持环境变量覆盖
  - [ ] 配置默认值和验证规则

### 第三阶段：MCP 工具实现

- [ ] 3.1 `parse_pdf` 工具
  - [ ] 定义工具 schema（使用 Pydantic 模型）
  - [ ] 实现 PDF 文件路径验证
  - [ ] 调用 MinerU API 提交任务
  - [ ] 返回 `task_id` 和初始状态
  - [ ] 支持所有后端类型参数
  - [ ] 添加参数验证和错误处理

  - [ ] 历史方案：3.2 `get_task_status` 工具
  - [ ] 定义工具 schema
  - [ ] 实现任务状态查询
  - [ ] 解析并返回状态信息
  - [ ] 处理任务不存在的情况

  - [ ] 历史方案：3.3 `extract_markdown` 工具
  - [ ] 定义工具 schema
  - [ ] 下载任务结果 ZIP
  - [ ] 使用 `zipfile` 解压
  - [ ] 提取 Markdown 内容
  - [ ] 返回解析后的文本
  - [ ] 处理文件不存在的情况

  - [ ] 历史方案：3.4 `list_supported_backends` 工具
  - [ ] 定义工具 schema
  - [ ] 返回支持的后端列表和描述

### 第四阶段：一体化容器构建

- [ ] 4.1 创建 Dockerfile
  - [ ] 基于 `rocm/pytorch` 或 `python:3.10-slim`
  - [ ] 安装 MinerU 依赖
  - [ ] 安装 MCP 服务器依赖
  - [ ] 复制项目代码
  - [ ] 配置启动脚本

- [ ] 4.2 创建启动脚本
  - [ ] 创建 `scripts/start.sh`
  - [ ] 启动 MinerU FastAPI 服务（后台）
  - [ ] 等待 MinerU 服务就绪
  - [ ] 启动 MCP 服务器
  - [ ] 或使用 `supervisord` 管理多个进程

- [ ] 4.3 创建 Docker Compose
  - [ ] 创建 `docker-compose.yml`
  - [ ] 配置 ROCm/GPU 支持
  - [ ] 配置端口映射（可选，用于 HTTP 模式）
  - [ ] 配置环境变量
  - [ ] 配置卷挂载

- [ ] 4.4 测试容器构建
  - [ ] 本地构建测试
  - [ ] 验证 MinerU 服务启动
  - [ ] 验证 MCP 服务器连接

### 第五阶段：增强功能

- [ ] 5.1 HTTP 模式支持
  - [ ] 使用 `fastapi` 创建 HTTP 接口
  - [ ] 历史方案：实现 `/mcp/invoke` 端点
  - [ ] 支持 Bearer Token 认证
  - [ ] 添加 CORS 支持

- [ ] 5.2 批量处理支持
  - [ ] 实现 `parse_pdf_batch` 工具
  - [ ] 并发提交多个任务
  - [ ] 批量状态查询

- [ ] 5.3 图片解析支持
  - [ ] 实现 `parse_image` 工具
  - [ ] 支持 PNG、JPG 格式

### 第六阶段：测试与优化

- [ ] 6.1 单元测试
  - [ ] 使用 `pytest` 设置测试框架
  - [ ] 编写 MinerU 客户端测试
  - [ ] 编写工具逻辑测试
  - [ ] 使用 `respx` 或 `pytest-httpx` Mock API

- [ ] 6.2 集成测试
  - [ ] 测试与真实 MinerU 服务的集成
  - [ ] 测试容器启动流程
  - [ ] 测试 MCP 客户端连接

- [ ] 6.3 性能优化
  - [ ] 添加连接池
  - [ ] 优化大文件处理
  - [ ] 实现结果缓存

### 第七阶段：文档与发布

- [ ] 7.1 完善文档
  - [ ] 更新 README.md 使用说明
  - [ ] 编写 Docker 部署指南
  - [ ] 添加 MCP 客户端配置示例
  - [ ] 编写故障排查指南

- [ ] 7.2 发布准备
  - [ ] 版本号管理
  - [ ] 创建 GitHub Release
  - [ ] 发布 Docker 镜像到 Docker Hub
  - [ ] 编写 CHANGELOG.md

## 项目结构

> Historical note
>
> 以下目录结构和命名属于早期规划草稿，已与当前实现不同步。
> 当前真实代码结构请以 `mcp-server/README.md` 为准。

```
mineru/
├── mcp-server/                 # MCP 服务器代码
│   ├── src/mineru_mcp/         # Python 包
│   │   ├── __init__.py
│   │   ├── api.py              # REST API
│   │   ├── app.py              # Unified app
│   │   ├── server.py           # MCP 工具实现
│   │   ├── config.py           # 配置管理
│   │   └── task_queue/         # 任务队列实现
│   ├── pyproject.toml          # Python 项目配置
│   ├── requirements.txt        # 生产依赖
│   ├── requirements-dev.txt    # 开发依赖
│   └── Dockerfile              # MCP 服务器单独构建（可选）
├── docs/                       # 文档
│   ├── README.md
│   └── TODO.md
├── scripts/
│   └── start.sh                # 一体化启动脚本
├── Dockerfile                  # All-in-One 镜像
├── docker-compose.yml          # 一体化部署配置
└── .env.example                # 环境变量示例
```

## 环境变量

> 说明：以下表格只保留当前一体化镜像和 MCP Server 直接相关的主要变量，不再展开历史草案配置。

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MCP_SERVER_MODE` | 运行模式: `stdio` 或 `http` | `stdio` |
| `MCP_SERVER_NAME` | MCP 服务器名称 | `mineru-mcp-server` |
| `MCP_HTTP_PORT` | HTTP 模式端口 | `8002` |
| `MINERU_ADMIN_INITIAL_PASSWORD` | 首次初始化 admin 账号时使用的初始密码 | `admin123` |
| `MINERU_VL_SERVER` | 远程 OpenAI-compatible VLM 服务地址 | - |
| `LOG_LEVEL` | 日志级别 | `INFO` |

## 使用方式

### 方式 1：stdio 模式（推荐用于桌面客户端）

```bash
# 启动一体化容器
docker run -d \
  --name mineru-mcp \
  -v $(pwd)/input:/input \
  -v $(pwd)/output:/output \
  -e MINERU_VL_SERVER=http://your-vlm-server:8000/v1 \
  mineru-mcp-all-in-one:latest

# MCP 客户端配置 (Claude Desktop)
{
  "mcpServers": {
    "mineru": {
      "command": "docker",
      "args": ["exec", "-i", "mineru-mcp", "mineru-mcp"],
      "env": {}
    }
  }
}
```

### 方式 2：HTTP 模式

```bash
# 启动容器并暴露 MCP HTTP 端口
docker run -d \
  --name mineru-mcp \
  -p 8002:8002 \
  -e MCP_SERVER_MODE=http \
  mineru-mcp-all-in-one:latest

# MCP Streamable HTTP 入口
# 请先通过 admin console 创建 caller，再使用 caller API key 调用
curl -X POST http://localhost:8002/mcp \
  -H "Authorization: Bearer <caller_api_key>" \
  -H "Content-Type: application/json" \
  -H "Mcp-Method: initialize" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {},
      "clientInfo": {"name": "example-client", "version": "1.0.0"}
    }
  }'
```

## 开发规范

### 代码风格
- 使用 `black` 格式化代码
- 使用 `ruff` 进行代码检查
- 使用 `mypy` 进行类型检查
- 函数和类添加 docstring

### 提交规范
- 使用 Conventional Commits 规范
- 格式: `<type>(<scope>): <subject>`

## 参考资源

- [MinerU 官方文档](https://mineru.readthedocs.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [httpx 文档](https://www.python-httpx.org/)

## 注意事项

1. **进程管理**: 一体化容器需要同时管理 MinerU 和 MCP 两个进程，使用 `supervisord` 或自定义脚本
2. **健康检查**: 需要确保 MinerU 服务完全启动后再启动 MCP 服务器
3. **文件路径**: MCP 服务器通过 stdio 通信，需要注意容器内外的文件路径映射
4. **日志输出**: stdio 模式下，日志不能输出到 stdout，需要输出到 stderr 或文件
5. **信号处理**: 正确处理 Docker 容器的信号，确保优雅关闭

## 更新日志

### 2024-04-11
- 重新设计为 Python 版本
- 规划一体化容器架构
- 定义两种运行模式（stdio/HTTP）
- 更新技术栈和项目结构
