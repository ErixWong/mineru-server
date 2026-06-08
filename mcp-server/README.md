# mineru-mcp

`mineru-mcp` 是本仓库中的 Python 包，提供：

- `mineru-mcp` CLI
- `/api` REST API
- `/mcp` Streamable HTTP MCP 服务
- 本地任务队列与 MinerU 集成适配层

这份 README 是 **包级 README**，主要用于 `pyproject.toml` 的 `readme` 字段和包元数据展示。

项目级说明、部署方式、接口清单、调用示例，请优先查看仓库根目录 `README.md`。

## 包定位

当前包负责四层能力：

1. REST API
2. MCP Tools
3. 本地任务队列
4. 上游 MinerU 适配层

代码目录：

```text
mcp-server/
├── pyproject.toml
├── README.md
├── src/mineru_mcp/
│   ├── api.py
│   ├── app.py
│   ├── cli.py
│   ├── mineru_adapter.py
│   ├── mineru_worker.py
│   ├── server.py
│   └── task_queue/
└── tests/
```

## 安装

需要 Python `>=3.10,<3.14`。

```bash
cd mcp-server
pip install -e .
```

当前包已将 `mineru` 声明为正式依赖。

## CLI

```bash
# stdio 模式
mineru-mcp

# HTTP 模式
mineru-mcp --mode http --port 8001
```

## 暴露能力

### REST

- `POST /api/tasks`
- `POST /api/uploads`
- `POST /api/uploads/submit`
- `POST /api/tasks/from-upload`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/deliverables/default`
- `GET /api/tasks/{task_id}/deliverables`
- `GET /api/tasks/{task_id}/deliverables/download?download_key=...`
- `GET /api/tasks/{task_id}/deliverables/images`
- `GET /api/tasks/{task_id}/deliverables/images/{image_name}`
- `DELETE /api/tasks/{task_id}`

兼容旧路径：

- `GET /api/tasks/{task_id}/result`
- `GET /api/tasks/{task_id}/artifacts`
- `GET /api/tasks/{task_id}/artifacts/download?download_key=...`
- `GET /api/tasks/{task_id}/images`
- `GET /api/tasks/{task_id}/images/{image_name}`

### MCP Tools

- `create_task_from_file`
- `create_task_from_upload`
- `get_task_status`
- `get_default_deliverable`
- `list_deliverables`
- `download_deliverable`
- `get_image_deliverables`
- `cancel_task`
- `list_tasks`
- `list_parsing_backends`
- `list_supported_file_formats`

兼容旧工具：

- `get_task_result`
- `list_task_results`
- `download_task_artifact`
- `get_task_images`

## 文档入口

- 项目主 README：`../README.md`
- API 总览：`../docs/README.md`
- MinerU 与 backend 说明：`../docs/mineru/models-and-backends.md`

## 说明

- 这份 README 不再承担项目总文档职责
- 根目录 `README.md` 是当前实现的主入口文档
- 历史设计文档不应作为当前接口契约依据

✌Bazinga！
