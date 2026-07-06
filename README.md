# MinerU MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

面向远程调用和 MCP 客户端的 MinerU 解析服务。

当前实现将三类能力整合到一个服务中：

- REST API：提交任务、轮询状态、列出交付物、按 artifact 下载结果
- MCP Tools：提供明确命名的任务创建、状态查询、artifact-first 结果读取能力
- 本地任务队列：SQLite 持久化、并发控制、取消与超时处理

仓库地址：`https://github.com/ErixWong/mineru-server`

## 当前能力

- 异步任务解析，返回 `task_id` 后轮询结果
- 支持两类提交方式：直接上传、上传后立即提交
- 支持按 `task_id` 访问提取图片的静态文件 URL
- 图片接口返回 Markdown 引用位置元数据
- MCP tool 命名已按资源和动作彻底收敛
- `mineru` 已作为正式依赖声明，不再依赖运行时 `sys.path` 注入

## 项目结构

```text
mineru-server/
├── mcp-server/                 # 服务端源码与测试
│   ├── src/mineru_mcp/         # REST、MCP、任务队列、MinerU 适配层
│   └── tests/                  # Python 测试
├── docs/                       # 设计、部署、任务记录
├── Dockerfile                  # All-in-One 镜像构建
├── docker-compose.yml          # 本地/服务器部署
└── .env.example                # 环境变量示例
```

## 快速开始

### Docker 部署

推荐使用 Docker。默认 `docker-compose.yml` 会直接拉取已发布镜像 `ericwong/mineru:mcp-3.1.15` 并启动统一服务。

当前 Dockerfile 已固定上游 MinerU tag：`mineru-3.1.15-released`，避免构建时直接跟随 `master` 漂移。

```bash
git clone https://github.com/ErixWong/mineru-server.git
cd mineru-server
cp .env.example .env
docker compose up -d
curl http://localhost:8002/health
```

### 本地运行

本地运行需要 Python `3.10` 到 `3.13`，并确保 MinerU 运行所需系统依赖可用。

```bash
cd mcp-server
pip install -e .

# stdio 模式
mineru-mcp

# HTTP 模式
mineru-mcp --mode http --port 8002
```

## 核心接口

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 简化健康检查（仅基本信息，无队列统计） |
| `GET` | `/api/health` | 完整健康检查（含队列统计） |
| `POST` | `/api/tasks` | multipart 上传并创建任务 |
| `POST` | `/api/uploads` | 预上传文件，返回 `upload_id` |
| `POST` | `/api/uploads/submit` | 上传后立即创建任务，推荐 |
| `POST` | `/api/tasks/from-upload` | 基于 `upload_id` 创建任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态；完成态默认兼容返回 Markdown |
| `GET` | `/api/tasks/{task_id}/deliverables/default` | 获取默认主交付物，或按 `format` 获取逻辑结果 |
| `GET` | `/api/tasks/{task_id}/deliverables` | 获取任务交付物清单 |
| `GET` | `/api/tasks/{task_id}/deliverables/download?download_key=...` | 按统一 `download_key` 下载单个交付物（原始内容） |
| `GET` | `/api/tasks/{task_id}/deliverables/images` | 获取图片交付物视图、静态 URL、Markdown 引用位置 |
| `GET` | `/api/tasks/{task_id}/deliverables/images/{image_name}` | 直接访问单张图片交付物 |
| `GET` | `/api/tasks/{task_id}/result` | 【兼容-已弃用】旧结果读取路径 |
| `GET` | `/api/tasks/{task_id}/artifacts` | 【兼容-已弃用】旧交付物列表路径 |
| `GET` | `/api/tasks/{task_id}/artifacts/download?download_key=...` | 【兼容-已弃用】旧 artifact 下载路径 |
| `GET` | `/api/tasks/{task_id}/images` | 【兼容-已弃用】旧图片读取路径 |
| `GET` | `/api/tasks/{task_id}/images/{image_name}` | 【兼容-已弃用】旧单图读取路径 |
| `DELETE` | `/api/tasks/{task_id}` | 取消任务 |
| `GET` | `/api/backends` | 查看支持的解析后端 |

> **健康检查说明**：
> - `/health` - 简化版，用于 Kubernetes liveness probe 等场景
> - `/api/health` - 完整版，包含队列统计信息

### MCP Tools

当前 MCP 暴露 16 个工具（含 6 个主工具 + 10 个兼容/辅助工具）：

> **主工具目标说明**：根据 task-018 审计决议，最终目标为 5 个主工具。当前为平稳过渡期，临时保留 6 个主工具。

| Tool | 说明 | 状态 |
|------|------|------|
| `create_task` | 统一任务创建（支持 file_base64 或 upload_id） | **主工具**（最终保留） |
| `get_task_status` | 查询任务状态 | **主工具**（最终保留） |
| `list_deliverables` | 列出当前任务可用交付物 | **主工具**（最终保留） |
| `download_deliverable` | 按 download_key 下载单个交付物 | **主工具**（最终保留） |
| `cancel_task` | 取消任务 | **主工具**（最终保留） |
| `get_default_deliverable` | 获取默认主交付物，支持按格式获取逻辑结果 | **主工具**（过渡期，目标：合并到 download_deliverable） |
| `create_task_from_file` | [DEPRECATED] 以 file_base64 创建任务 | 兼容（将移除） |
| `create_task_from_upload` | [DEPRECATED] 基于 upload_id 创建任务 | 兼容（将移除） |
| `get_task_result` | [DEPRECATED] 旧结果读取工具 | 兼容（将移除） |
| `list_task_results` | [DEPRECATED] 旧结果列表工具 | 兼容（将移除） |
| `download_task_artifact` | [DEPRECATED] 旧 artifact 下载工具 | 兼容（将移除） |
| `get_image_deliverables` | [DEPRECATED] 图片交付物（Base64） | 兼容（将移除） |
| `get_task_images` | [DEPRECATED] 旧图片读取工具 | 兼容（将移除） |
| `list_tasks` | 列出任务 | 辅助 |
| `list_parsing_backends` | [DEPRECATED] 列出解析后端（静态信息） | 兼容（将移除） |
| `list_supported_file_formats` | [DEPRECATED] 列出支持格式（静态信息） | 兼容（将移除） |

> **最终主工具集**（目标 5 个）：
> 1. `create_task` - 任务创建
> 2. `get_task_status` - 任务状态查询
> 3. `list_deliverables` - 交付物列表
> 4. `download_deliverable` - 交付物下载（含默认格式快捷支持）
> 5. `cancel_task` - 任务取消
>
> **关于 get_default_deliverable**：该工具计划在后续版本中合并到 `download_deliverable`，作为其默认格式快捷方式。当前作为单独主工具保留，以便平稳过渡。
>
> **兼容工具**：仅保留过渡支持，预计在 0.4.0 版本移除。

MCP HTTP 入口：

- `POST /mcp/`

## 推荐调用路径

### 1. 普通远程调用

推荐用一跳接口，不让调用方记住 `upload_id`：

```bash
curl -X POST http://localhost:8002/api/uploads/submit \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.pdf" \
  -F "backend=hybrid-http-client" \
  -F "lang=ch"
```

返回：

```json
{
  "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "message": "Task submitted successfully",
  "created_at": "2026-06-07T15:45:00"
}
```

后续轮询：

```bash
curl -H "Authorization: Bearer your-token" \
  "http://localhost:8002/api/tasks/{task_id}?return_md=false"
```

推荐先列交付物，再下载：

```bash
curl -H "Authorization: Bearer your-token" \
  http://localhost:8002/api/tasks/{task_id}/deliverables
```

再按 `download_key` 下载：

```bash
curl -H "Authorization: Bearer your-token" \
  "http://localhost:8002/api/tasks/{task_id}/deliverables/download?download_key=document/vlm/document.md"
```

兼容读取结果：

```bash
curl -H "Authorization: Bearer your-token" \
  http://localhost:8002/api/tasks/{task_id}/result
```

读取特定结果格式：

```bash
curl -H "Authorization: Bearer your-token" \
  "http://localhost:8002/api/tasks/{task_id}/deliverables/default?format=content_list"
```

查看当前任务有哪些结果可取：

```bash
curl -H "Authorization: Bearer your-token" \
  http://localhost:8002/api/tasks/{task_id}/deliverables
```

### 2. 分阶段上传

适合需要先上传、再由别的流程决定是否提交任务的场景：

```bash
curl -X POST http://localhost:8002/api/uploads \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.pdf"

curl -X POST http://localhost:8002/api/tasks/from-upload \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "upl_123456",
    "backend": "hybrid-http-client",
    "lang": "ch"
  }'
```

### 3. MCP 调用

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_task",
    "arguments": {
      "file_base64": "<base64>",
      "file_name": "document.pdf",
      "backend": "hybrid-http-client",
      "lang": "ch"
    }
  }
}
```

> **提示**：`create_task` 支持两种调用方式：
> - `file_base64`：直接上传 Base64 编码的文件内容
> - `upload_id`：基于预上传的文件 ID 创建任务（适用于大文件或需要分阶段上传的场景）

完成后查询：

- `get_task_status`
- `list_deliverables`
- `download_deliverable`

## 图片结果

> **重要说明**：图片已纳入统一 Deliverables 模型。主读取路径为：
> - `list_deliverables` - 列出所有交付物（含图片）
> - `download_deliverable` - 下载任意交付物（含图片）
>
> 以下兼容路径仍可用，但仅作为过渡支持，预计在 0.4.0 版本移除。

### 兼容路径（过渡期）

1. `GET /api/tasks/{task_id}/images`
返回：
- `images`：`filename -> data:image/...;base64,...`
- `items[]`：结构化图片元数据

2. `GET /api/tasks/{task_id}/images/{image_name}`
返回：
- 图片二进制文件，可直接给前端 `<img src>` 或第三方系统使用

`items[]` 当前包含：

- `filename`
- `relative_path`
- `url`
- `media_type`
- `referenced_in_markdown`
- `references[]`

`references[]` 表示图片在 Markdown 文本中的引用位置，包括：

- `markdown_path`
- `line_number`
- `start_offset`
- `end_offset`
- `alt_text`

注意：这些位置是 **Markdown 文本位置**，不是 PDF 页码或 bbox 坐标。

## 联调注意事项

- 当前项目默认 HTTP 端口为 `8002`
- MCP Streamable HTTP 入口建议直接使用 `POST /mcp/`
- 如果请求先打到 `/mcp`，服务会重定向到 `/mcp/`；部分客户端在重定向后会丢失 `Authorization` 头，进而返回 `401`
- 在未配置外部 VLM 服务时，真实 PDF 联调优先使用 `pipeline` 后端；`hybrid-http-client` 和 `vlm-http-client` 依赖额外的 VLM 配置
- 真实图文混编联调可使用样本：`tests/奇瑞质量协议签章版-1-2.pdf`

## 输出目录

服务内部产物默认写入 `output/`，可通过 `MINERU_OUTPUT_ROOT` 调整。

典型结构：

```text
output/YYYY/MM/DD/{task_id}/
├── input.pdf
└── input/{backend_output_dir}/
    ├── input.md
    ├── input_middle.json
    ├── input_model.json
    ├── input_content_list.json
    ├── input_content_list_v2.json
    └── images/
        ├── image_001.jpg
        └── image_002.png
```

其中：

- `vlm-http-client` -> `vlm`
- `pipeline` -> `auto`
- `hybrid-http-client` -> `hybrid_auto`

当前产物契约：

- 必需产物：`md`, `middle_json`
- 推荐产物：`content_list`, `content_list_v2`
- 可选产物：`model_json`

说明：

- `content_list_v2` 是上游自 `3.0` 起新增的统一结构化输出
- 但上游当前仍将其标注为 `development version, subject to change`
- 因此本项目已纳入结果认知，但暂不将其当作稳定公开契约核心字段
- `model_json` 现在会默认生成，更适合调试和底层二次开发，不是主结果接口

## 解析后端

| 后端 | 说明 | GPU |
|------|------|-----|
| `hybrid-http-client` | 本地 OCR + 远程 VLM，推荐 | 不需要 |
| `vlm-http-client` | 远程 VLM API | 不需要 |
| `pipeline` | 传统流水线，无 VLM | 不需要 |
| `vlm-auto-engine` | 本地 VLM | 需要 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 需要 |

## 关键配置

完整环境变量说明以 `mcp-server/README.md` 为准。最常用的是：

```bash
# 服务
MCP_SERVER_MODE=http
MCP_HTTP_PORT=8002
MCP_HTTP_AUTH_TOKEN=your-token

# 输出与任务队列
MINERU_OUTPUT_ROOT=output
MINERU_DB_PATH=output/tasks.db
MINERU_DEFAULT_BACKEND=hybrid-http-client

# 远程 VLM（http-client 后端需要）
MINERU_VL_SERVER=https://api.openai.com/v1
MINERU_VLM_API_KEY=sk-your-key
MINERU_VLM_MODEL=gpt-4o
```

## 当前实现约束

- 所有解析任务都是异步任务
- MCP 小文件直传仍使用 `file_base64`
- 大文件远程调用优先推荐 `POST /api/uploads/submit`
- 当前图片位置只提供 Markdown 引用位置，不提供 PDF 坐标
- 上游 MinerU 仍通过适配层接入，当前适配层封装在 `mineru_adapter.py`

## 文档索引

- [详细服务文档](mcp-server/README.md)
- [API 文档总览](docs/README.md)
- [模型与后端说明](docs/mineru/models-and-backends.md)
- [MinerU 容器调用说明](docs/mineru/container_usage.md)
- [Strix Halo 部署指南](docs/deployment/strix-halo/deployment.md)

## 说明

- 根目录 `README.md` 是项目主入口文档
- `mcp-server/README.md` 仅保留包级说明和 Python 包元数据用途
- 当前对外接入应以本 README 与 `docs/README.md` 为主
- `mcp-server/docs/TODO.md` 与 `mcp-server/docs/research_notes.md` 为历史材料，不作为当前接口契约

## 许可证

MIT License

## 致谢

- [MinerU](https://github.com/opendatalab/MinerU)
- [Model Context Protocol](https://modelcontextprotocol.io/)

✌Bazinga！
