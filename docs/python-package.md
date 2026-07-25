# mineru-mcp Python 包说明

`mineru-mcp` 是本仓库中的 Python 包，提供：

- `mineru-mcp` CLI
- `/api` REST API
- `/mcp` Streamable HTTP MCP 服务
- 本地任务队列与 MinerU 集成适配层

这份文档是包级说明归档。项目级说明、部署方式、接口清单、调用示例，以仓库根目录 `README.md` 为准。

## 包定位

当前包负责四层能力：

1. REST API
2. MCP Tools
3. 本地任务队列
4. 上游 MinerU 适配层

代码目录：

```text
mineru-server/
├── pyproject.toml
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

## 文档入口

- 项目主 README：[`../README.md`](../README.md)
- 文档索引：[`README.md`](README.md)
- MinerU backend 说明：[`mineru/models-and-backends.md`](mineru/models-and-backends.md)