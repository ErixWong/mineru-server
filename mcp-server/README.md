# mineru-mcp

`mineru-mcp` 是本仓库中的 Python 包，提供：

- `mineru-mcp` CLI
- `/api` REST API
- `/mcp` Streamable HTTP MCP 服务
- 本地任务队列与 MinerU 集成适配层

这份 README 是 **包级 README**，主要用于 `pyproject.toml` 的 `readme` 字段和包元数据展示。

项目级说明、部署方式、接口清单、调用示例，请只查看仓库根目录 `README.md`。本文件不再承担当前实现主说明职责。

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
py -3.13 -m pip install -e .
```

当前包已将 `mineru` 声明为正式依赖。

## CLI

```bash
# stdio 模式
py -3.13 -m mineru_mcp.cli

# HTTP 模式
py -3.13 -m mineru_mcp.cli --mode http --port 8002
```

## 暴露能力

### REST

当前公开主路径、兼容路径与完整调用说明，以仓库根目录 `README.md` 为准。本文件不再重复维护详细 REST 清单，避免与项目主文档漂移。

### MCP Tools

当前 MCP tools 数量、名称和主/辅分类，以仓库根目录 `README.md` 为准。本文件不再重复维护详细 tool 清单，避免与项目主文档漂移。

## 文档入口

- 项目主 README：`../README.md`
- 文档索引：`../docs/README.md`
- MinerU 与 backend 说明：`../docs/mineru/models-and-backends.md`

## 说明

- 这份 README 不再承担项目总文档职责
- 根目录 `README.md` 是当前实现的唯一主入口文档
- `docs/README.md` 是文档索引，不是项目主说明
- 历史设计文档不应作为当前接口契约依据

✌Bazinga！