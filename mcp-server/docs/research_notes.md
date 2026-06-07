# MCP Server 研究笔记

本文档记录三项关键技术研究的结论。

> Historical note
>
> 本文档用于保留早期研究过程，其中部分示例基于旧目录结构、旧工具名和“外部 MCP Server 包装 MinerU FastAPI”的早期方案。
> 当前实现已经演进为统一 Starlette 应用，同时挂载 `/api` 与 `/mcp`。
>
> 当前实现基线请以：
> - `README.md`
> - `docs/README.md`
> - `mcp-server/README.md`
> 为准。

## 1. 一体化容器启动脚本

### 问题
如何在同一个容器中同时启动 MinerU FastAPI 和 MCP Server？

### 方案分析

#### 方案 A：进程管理器（supervisord）
- 使用 supervisord 管理多个进程
- 优点：进程监控、自动重启、日志管理
- 缺点：额外依赖、配置复杂

#### 方案 B：Shell 脚本后台启动
```bash
#!/bin/bash
# 启动 MinerU FastAPI（后台）
uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 8000 &
MINERU_PID=$!

# 等待 MinerU 就绪
until curl -s http://localhost:8000/health > /dev/null; do
    sleep 1
done

# 启动 MCP Server
python -m mcp_server.server --transport streamable-http --port 8001

# 清理
kill $MINERU_PID
```
- 优点：简单、无额外依赖
- 缺点：进程管理较弱

#### 方案 C：Python 统一入口（推荐）
```python
import asyncio
import multiprocessing
import uvicorn
from mcp.server.fastmcp import FastMCP

def run_mineru():
    """MinerU FastAPI 进程"""
    uvicorn.run("mineru.cli.fast_api:app", host="0.0.0.0", port=8000)

async def run_mcp():
    """MCP Server 异步任务"""
    mcp = FastMCP("MinerU MCP Server")
    # ... 定义 tools
    await mcp.run(transport="streamable-http")

def main():
    # MinerU 在独立进程运行
    mineru_process = multiprocessing.Process(target=run_mineru)
    mineru_process.start()
    
    # 等待 MinerU 就绪
    import time
    while True:
        try:
            import httpx
            httpx.get("http://localhost:8000/health").raise_for_status()
            break
        except:
            time.sleep(1)
    
    # MCP Server 在主进程运行
    asyncio.run(run_mcp())
    
    # 清理
    mineru_process.terminate()
```

### 推荐方案
**方案 C（Python 统一入口）**

理由：
1. 复用 MinerU 已有的 `multiprocessing` + `uvicorn` 模式
2. 无额外依赖
3. 进程管理清晰
4. 容器入口点统一

### 实现细节

**启动顺序**：
1. MinerU FastAPI 先启动（端口 8000）
2. 等待 `/health` 返回成功
3. MCP Server 启动（端口 8001）

**端口分配**：
- MinerU FastAPI: `8000`
- MCP Server (HTTP): `8001`
- MCP Server (stdio): 无端口

**环境变量**：
```bash
MINERU_API_HOST=0.0.0.0
MINERU_API_PORT=8000
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8001
MCP_TRANSPORT=streamable-http  # 或 stdio
```

---

## 2. MCP SDK 具体使用方式

### FastMCP 核心概念

从官方文档提取的关键信息：

#### 创建 Server
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "MinerU MCP Server",
    # 推荐配置
    stateless_http=True,   # 无状态模式，适合生产
    json_response=True,    # JSON 响应，而非 SSE
)
```

#### 定义 Tool
```python
@mcp.tool()
def parse_pdf(file_path: str) -> dict:
    """解析 PDF 文件
    
    Args:
        file_path: PDF 文件路径
        
    Returns:
        解析结果，包含 markdown 内容
    """
    # 调用 MinerU FastAPI
    return {"status": "success", "content": "..."}
```

#### 使用 Context（进度报告）
```python
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

@mcp.tool()
async def parse_pdf_large(
    file_path: str,
    ctx: Context[ServerSession, None]
) -> str:
    """解析大型 PDF"""
    await ctx.info("开始解析...")
    await ctx.report_progress(0.5, 1.0, "处理中...")
    return "完成"
```

#### 运行模式

**stdio 模式**（桌面 MCP 客户端）：
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**streamable-http 模式**（远程调用）：
```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

#### 挂载到现有 ASGI 服务器
```python
from starlette.applications import Starlette
from starlette.routing import Mount

# MinerU 已有 FastAPI app
from mineru.cli.fast_api import app as mineru_app

# MCP Server
mcp = FastMCP("MinerU MCP", stateless_http=True, json_response=True)
mcp.settings.streamable_http_path = "/"

# 组合应用
app = Starlette(routes=[
    Mount("/api", app=mineru_app),      # MinerU API
    Mount("/mcp", app=mcp.streamable_http_app()),  # MCP
])
```

### MCP Tools 设计

针对 MinerU 的 MCP Tools：

| Tool | 描述 | 参数 |
|------|------|------|
| `submit_task` | 提交 PDF/图片任务 | `file_base64`, `file_name`, `backend` |
| `get_task` | 获取异步任务状态和结果 | `task_id` |
| `get_images` | 获取提取图片 | `task_id` |
| `list_backends` | 列出支持的 backend | 无 |

### 调用 MinerU FastAPI

使用 `httpx`（MinerU 已有依赖）：

```python
import httpx

async def call_mineru_parse(file_path: str) -> dict:
    async with httpx.AsyncClient() as client:
        # 上传文件
        with open(file_path, "rb") as f:
            response = await client.post(
                "http://localhost:8000/file_parse",
                files={"files": f},
                data={"backend": "hybrid-http-client", "return_md": True}
            )
        return response.json()
```

---

## 3. Dockerfile 构建方案

### 基础镜像选择

**方案 A：基于 MinerU 官方镜像**
```dockerfile
FROM opendatalab/mineru:latest

# 添加 MCP Server
COPY mcp-server/ /app/mcp-server/
WORKDIR /app/mcp-server
RUN pip install mcp

# 启动脚本
COPY entrypoint.py /app/entrypoint.py
CMD ["python", "/app/entrypoint.py"]
```

**方案 B：从源码构建**
```dockerfile
FROM python:3.10-slim

# 安装 MinerU
RUN pip install mineru

# 安装 MCP SDK
RUN pip install mcp

# 复制 MCP Server
COPY mcp-server/ /app/mcp-server/

# 启动
WORKDIR /app
COPY entrypoint.py .
CMD ["python", "entrypoint.py"]
```

### 推荐方案

**方案 A（基于 MinerU 官方镜像）**

理由：
1. MinerU 依赖复杂（PyTorch、OCR 模型等），官方镜像已预装
2. 减少构建时间
3. 确保兼容性

### Dockerfile 示例

```dockerfile
# 基于 MinerU 官方镜像
FROM opendatalab/mineru:latest

# 安装 MCP SDK
RUN pip install --no-cache-dir mcp

# 复制 MCP Server 代码
COPY mcp-server/src/mineru_mcp/ /app/mineru_mcp/
COPY mcp-server/pyproject.toml /app/

# 复制统一启动脚本
COPY mcp-server/entrypoint.py /app/entrypoint.py

# 设置工作目录
WORKDIR /app

# 环境变量
ENV MINERU_API_HOST=0.0.0.0
ENV MINERU_API_PORT=8000
ENV MCP_SERVER_HOST=0.0.0.0
ENV MCP_SERVER_PORT=8001
ENV MCP_TRANSPORT=streamable-http

# 暴露端口
EXPOSE 8000 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health && curl -f http://localhost:8001/health || exit 1

# 启动
CMD ["python", "/app/entrypoint.py"]
```

### ROCm 版本（AMD GPU）

```dockerfile
# 基于 ROCm PyTorch 镜像
FROM rocm/pytorch:rocm6.2_ubuntu22.04_py3.10_pytorch2.5.1

# 安装 MinerU（从源码）
RUN pip install git+https://github.com/opendatalab/MinerU.git

# 安装 MCP SDK
RUN pip install mcp

# ... 其余同上
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  mineru-mcp:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"  # MinerU API
      - "8001:8001"  # MCP Server
    environment:
      - MINERU_API_ENABLE_VLM_PRELOAD=0
      - VLM_SERVER_URL=http://vlm-server:30000
    volumes:
      - ./output:/app/output
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 总结

| 问题 | 推荐方案 | 关键技术 |
|------|----------|----------|
| 一体化启动 | Python 统一入口 | `multiprocessing` + `asyncio` |
| MCP SDK | FastMCP + httpx | `@mcp.tool()` + `stateless_http=True` |
| Dockerfile | 基于官方镜像 | `opendatalab/mineru:latest` + `pip install mcp` |

### 下一步

1. 实现 `entrypoint.py` 统一启动脚本
2. 实现 MCP Server 核心代码
3. 创建 Dockerfile 和 docker-compose.yml
4. 测试 stdio 和 streamable-http 两种模式
