# MinerU MCP Server 文档

## 项目信息

- **仓库**: https://github.com/ErixWong/mineru-server
- **上游**: https://github.com/opendatalab/MinerU

## 文档定位

本页只承担**文档索引与导航**职责。

当前项目的唯一主入口文档是：

- 根目录 `README.md`

本页不再单独承担：

- 项目主说明
- 最终接口契约说明
- caller key 管理策略主说明

## 文档目录

```text
docs/
├── deployment/           # 部署文档
│   └── strix-halo/       # Strix Halo (AMD ROCm) 部署方案
├── mineru/               # MinerU 使用说明
├── design/               # 设计文档
└── tasks/                # 任务记录
```

## 快速开始

### Docker 部署

```bash
git clone https://github.com/ErixWong/mineru-server.git
cd mineru-server
export MINERU_CALLER_KEY_MASTER_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
docker compose up -d
```

访问：

- 管理台：`http://localhost:8002/admin/login`
- API：`http://localhost:8002/api/docs`

### 本地运行

```bash
cp .env.example .env
py -3.13 -m pip install -e .
py -3.13 -m mineru_mcp.cli --mode http --port 8002
```

> 说明：项目主运行口径以根目录 `README.md` 为准；本页只做概要导航。

## 镜像变体

项目提供两个 Dockerfile，按需求选择构建：

| | `Dockerfile`（完整版） | `Dockerfile.slim`（精简版） |
|---|---|---|
| **安装内容** | `mineru[vlm,pipeline,vllm]` | `mineru[pipeline]` |
| **体积（估算）** | ~12–16 GB | ~7–9 GB |
| **vLLM 本地推理** | ✅ | ❌ |
| **gradio Web UI** | ❌（已剔除，用 admin-ui SPA 替代） | ❌ |

| Backend | 完整版 | 精简版 |
|---|---|---|
| `pipeline` | ✅ | ✅ |
| `hybrid-http-client` | ✅ | ✅ |
| `vlm-http-client` | ✅ | ✅ |
| `vlm-auto-engine` | ✅ | ❌ |
| `hybrid-auto-engine` | ✅ | ❌ |

## 关键文档

| 文档 | 说明 |
|------|------|
| [../README.md](../README.md) | 项目唯一主入口文档 |
| [mineru/models-and-backends.md](mineru/models-and-backends.md) | MinerU 模型下载、Backend 选择、GPU 兼容性 |
| [mineru/backend-and-engine-dataflow.md](mineru/backend-and-engine-dataflow.md) | MinerU backend、engine 与 vLLM 数据链路说明 |
| [deployment/github-packages.md](deployment/github-packages.md) | GitHub Container Registry 镜像发布与清理策略 |
| [deployment/strix-halo/deployment.md](deployment/strix-halo/deployment.md) | Strix Halo 部署指南 |
| [mineru/container_usage.md](mineru/container_usage.md) | MinerU 容器调用 |
| [mineru/llm_requirements.md](mineru/llm_requirements.md) | LLM/VLM 配置 |
| [design/admin-management-console.md](design/admin-management-console.md) | 内部控制面设计与 caller/key 口径 |

## API 主路径摘要

以下仅列当前主路径摘要，完整说明以根 `README.md` 为准：

| 端点 | 功能 |
|------|------|
| `GET /health` | 简化健康检查 |
| `GET /api/health` | 完整健康检查 |
| `POST /api/tasks` | 提交任务 |
| `GET /api/tasks/{id}` | 查询状态 |
| `GET /api/tasks/{id}/deliverables` | 获取交付物清单 |
| `GET /api/tasks/{id}/deliverables/download?download_key=...` | 按统一 download_key 下载单个交付物 |
| `DELETE /api/tasks/{id}` | 取消任务 |
| `GET /api/backends` | 可用后端 |
| `POST /mcp` | MCP Streamable HTTP JSON-RPC 入口 |

> 说明：
> - 图片已纳入统一 deliverables 模型，主读取路径是 deliverables 列表与下载。
> - 本页不再重复维护旧兼容路径与详细调用说明，避免与根 README 漂移。

## 文档使用说明

- 根目录 `README.md` 是项目唯一主入口文档
- `docs/python-package.md` 仅用于包级说明归档
- `docs/design/*` 与部分专题文档用于设计沉淀，不替代当前接口契约
- 历史设计材料不能直接作为当前接口契约依据

## 解析后端

| 后端 | 说明 | GPU |
|------|------|-----|
| `hybrid-http-client` | 本地 OCR + 远程 VLM（推荐） | 不需要 |
| `vlm-http-client` | 远程 VLM | 不需要 |
| `pipeline` | 传统流水线（无 VLM） | 不需要 |
| `vlm-auto-engine` | 本地 VLM | 需要 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 需要 |

✌Bazinga！
