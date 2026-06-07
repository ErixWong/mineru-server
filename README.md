# MinerU MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

MinerU PDF 解析能力的 MCP (Model Context Protocol) 服务端实现。将 MinerU 的 PDF 解析能力通过 MCP 协议暴露给 MCP 客户端。

## 项目信息

- **仓库**: https://github.com/ErixWong/mineru-server
- **依赖**: MinerU (通过 Dockerfile git clone 构建)
- **版本**: v0.2.0

本项目是一个独立的 MCP Server，将 MinerU 的 PDF 解析能力通过 MCP 协议暴露给 AI 客户端。

## 功能特性

- **MCP Tools**: 6 个 MCP 工具（submit_task, get_task, get_images 等）
- **REST API**: HTTP API 端点（任务提交、状态查询）
- **任务队列**: SQLite 持久化 + 并发控制
- **认证**: Bearer Token 可选认证
- **Docker**: All-in-One 一键部署

## 快速开始

### Docker 部署（推荐）

```bash
# 克隆仓库
git clone https://github.com/ErixWong/mineru-server.git
cd mineru-server

# 配置环境变量
cp .env.example .env
# 编辑 .env 设置 VLM API（如 OpenAI）

# 启动服务
docker-compose up -d

# 访问服务
curl http://localhost:8001/health
```

### 本地运行

```bash
cd mcp-server
pip install -e .

# stdio 模式（桌面客户端）
mineru-mcp

# HTTP 模式（远程调用）
mineru-mcp --mode http --port 8001
```

## API 端点

| 端点 | 功能 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/tasks` | 提交解析任务（multipart 上传） |
| `POST /api/uploads` | 预上传文件并返回 `upload_id` |
| `POST /api/tasks/from-upload` | 基于 `upload_id` 提交解析任务 |
| `GET /api/tasks/{id}` | 查询任务状态 |
| `GET /api/tasks/{id}/result` | 获取 Markdown 结果 |
| `GET /api/tasks/{id}/images` | 获取提取的图片 |
| `DELETE /api/tasks/{id}` | 取消任务 |
| `GET /api/backends` | 列出解析后端 |
| `MCP /mcp` | MCP 协议端点 |

## 解析后端

| 后端 | 说明 | GPU |
|------|------|-----|
| `hybrid-http-client` | 本地 OCR + 远程 VLM（推荐） | 不需要 |
| `vlm-http-client` | 远程 VLM API | 不需要 |
| `pipeline` | 传统流水线（无 VLM） | 不需要 |
| `vlm-auto-engine` | 本地 VLM 引擎 | 需要 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 需要 |

## 配置

见 `.env.example` 文件，关键配置：

```bash
# VLM API（必须）
MINERU_VLM_BASE_URL=https://api.openai.com/v1
MINERU_VLM_API_KEY=sk-your-key
MINERU_VLM_MODEL=gpt-4o

# 默认后端
MINERU_DEFAULT_BACKEND=hybrid-http-client

# 认证（可选）
MCP_HTTP_AUTH_TOKEN=your-token
```

## 目录结构

```
mineru-server/
├── mcp-server/           # MCP Server 源码
│   ├── src/mineru_mcp/   # 核心模块
│   └── tests/            # 测试
├── docs/                 # 文档
│   ├── deployment/       # 部署指南（含 Strix Halo）
│   └── design/           # 设计文档
├── docker-compose.yml    # Docker Compose
├── Dockerfile            # All-in-One Dockerfile
└── .env.example          # 配置示例
```

## 文档

- [模型与 Backend 指南](docs/mineru/models-and-backends.md) - MinerU 模型下载、Backend 选择、GPU 兼容性
- [部署指南](docs/deployment/strix-halo/deployment.md) - Strix Halo 特定部署
- [MCP Server 文档](mcp-server/README.md) - 详细使用说明
- [API 文档](docs/README.md) - API 端点说明

## 文档状态说明

- 当前对外接入应以 `README.md`、`docs/README.md`、`mcp-server/README.md` 为准
- `mcp-server/docs/TODO.md` 与 `mcp-server/docs/research_notes.md` 主要保留历史设计过程，不应作为当前实现基线

## 许可证

MIT License

## 致谢

- [MinerU](https://github.com/opendatalab/MinerU) - PDF 解析引擎
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
