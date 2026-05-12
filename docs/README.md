# MinerU MCP Server 文档

## 项目信息

- **仓库**: https://github.com/ErixWong/mineru-server
- **上游**: https://github.com/opendatalab/MinerU

## 文档目录

```
docs/
├── deployment/           # 部署文档
│   └ strix-halo/        # Strix Halo (AMD ROCm) 部署方案
├── mineru/              # MinerU 使用说明
├── design/              # 设计文档
└── tasks/               # 任务记录
```

## 快速开始

### Docker 部署

```bash
git clone https://github.com/ErixWong/mineru-server.git
cd mineru-server
cp .env.example .env
docker compose up -d
```

### 本地运行

```bash
cd mcp-server
pip install -e .
mineru-mcp --mode http --port 8001
```

## 关键文档

| 文档 | 说明 |
|------|------|
| [mineru/models-and-backends.md](mineru/models-and-backends.md) | MinerU 模型下载、Backend 选择、GPU 兼容性 |
| [deployment/strix-halo/deployment.md](deployment/strix-halo/deployment.md) | Strix Halo 部署指南 |
| [mineru/container_usage.md](mineru/container_usage.md) | MinerU 容器调用 |
| [mineru/llm_requirements.md](mineru/llm_requirements.md) | LLM/VLM 配置 |

## API 端点

| 端点 | 功能 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/tasks` | 提交任务 |
| `GET /api/tasks/{id}` | 查询状态 |
| `GET /api/tasks/{id}/images` | 获取图片 |
| `GET /api/backends` | 可用后端 |

## 解析后端

| 后端 | 说明 | GPU |
|------|------|-----|
| `hybrid-http-client` | 本地 OCR + 远程 VLM（推荐） | 不需要 |
| `vlm-http-client` | 远程 VLM | 不需要 |
| `pipeline` | 传统流水线（无 VLM） | 不需要 |
| `vlm-auto-engine` | 本地 VLM | 需要 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 需要 |

✌Bazinga！