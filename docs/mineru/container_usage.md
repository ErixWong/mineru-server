# MinerU 容器调用指南与 MCP 支持

> Historical note
>
> 本文档主要讨论 MinerU 原生容器接口与早期 MCP 包装思路。
> 当前仓库中的正式 MCP 实现已演进为统一应用，实际代码与接口契约请优先参考：
> - `README.md`
> - `docs/README.md`
> - `docs/python-package.md`

## 1. MinerU 原生接口说明

**MinerU 本身不直接支持 MCP (Model Context Protocol)**，但它提供了多种原生接口方式：

| 接口类型 | 说明 | 适用场景 |
|---------|------|---------|
| **FastAPI HTTP API** | RESTful API 服务 | 程序化调用、集成到其他系统 |
| **CLI 命令行** | 命令行工具 | 脚本、批量处理 |
| **Gradio Web UI** | 浏览器界面 | 人工操作、演示 |
| **Router 服务** | 负载均衡/路由 | 多实例部署 |

## 2. 容器启动后的调用方式

### 认证方式说明

**MinerU 原生 FastAPI 服务没有内置 Bearer Token 认证**。如果需要认证，可以通过以下方式实现：

1. **反向代理层添加认证**（推荐）- 使用 Nginx/Traefik 等添加 Bearer Token 验证
2. **修改 FastAPI 代码** - 在 `src/mineru/cli/fast_api.py` 中添加依赖注入
3. **网络隔离** - 通过 Docker 网络限制访问，仅允许特定容器/服务访问

#### 方式一：HTTP API 调用（推荐）

容器启动后会暴露 FastAPI 服务，默认端口 `8000`：

```bash
# 1. 启动容器（以方案 A 为例）
cd docs
docker compose -f strix-halo-compose-scheme-a.yml up -d

# 2. 等待服务就绪（约 30-60 秒）
docker compose -f strix-halo-compose-scheme-a.yml ps

# 3. 查看 API 文档
curl http://localhost:8000/docs
```

#### 添加 Bearer Token 认证（可选）

如果需要添加 Bearer Token 认证，可以创建一个带认证的反向代理：

**创建 `nginx_auth.conf`：**
```nginx
server {
    listen 8080;
    
    # Bearer Token 验证
    set $expected_token "your-secret-token-here";
    
    if ($http_authorization != "Bearer $expected_token") {
        return 401 "Unauthorized";
    }
    
    location / {
        proxy_pass http://mineru-hybrid:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**修改 Docker Compose 添加 Nginx：**
```yaml
services:
  nginx-auth:
    image: nginx:alpine
    container_name: mineru-nginx-auth
    ports:
      - "8080:8080"
    volumes:
      - ./nginx_auth.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - mineru-hybrid
```

**带认证的 API 调用：**
```bash
curl -X POST "http://localhost:8080/parse" \
  -H "Authorization: Bearer your-secret-token-here" \
  -F "pdf_file=@document.pdf" \
  -F "backend=hybrid-http-client"
```

#### API 调用示例

**提交解析任务：**
```bash
curl -X POST "http://localhost:8000/parse" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "pdf_file=@/path/to/your/document.pdf" \
  -F "backend=hybrid-http-client" \
  -F "server_url=http://your-vlm-server:8000/v1" \
  -F "lang=ch" \
  -F "formula_enable=true" \
  -F "table_enable=true"
```

**响应示例：**
```json
{
  "task_id": "uuid-task-id",
  "status": "pending",
  "message": "Task submitted successfully"
}
```

**查询任务状态：**
```bash
curl "http://localhost:8000/tasks/{task_id}"
```

**获取解析结果：**
```bash
# 下载结果 ZIP
curl "http://localhost:8000/tasks/{task_id}/result" \
  -o output.zip

# 解压结果
unzip output.zip -d ./output/
```

### 方式二：CLI 命令调用

```bash
# 进入容器执行命令
docker compose -f strix-halo-compose-scheme-a.yml exec mineru-hybrid \
  mineru -p /input/document.pdf -o /output/ -b hybrid-http-client

# 或使用 mineru_launcher.py
docker compose -f strix-halo-compose-scheme-a.yml exec mineru-hybrid \
  python /workspace/mineru_launcher.py \
  -p /input/document.pdf \
  -o /output/ \
  -b hybrid-http-client \
  -u "http://your-vlm-server:8000/v1"
```

### 方式三：Gradio Web UI

```bash
# 启动带 Web UI 的容器
docker compose -f strix-halo-compose-scheme-a.yml --profile webui up -d

# 浏览器访问
open http://localhost:7860
```

## 3. 如何实现 MCP 支持

虽然 MinerU 原生不支持 MCP，但你可以创建一个 **MCP 服务器** 来包装 MinerU 的 API：

### 3.1 MCP 服务器实现示例

创建 `mineru_mcp_server.py`：

```python
#!/usr/bin/env python3
"""
MinerU MCP 服务器 - 包装 MinerU FastAPI 为 MCP 协议
"""

import asyncio
import json
import httpx
from typing import Any
from mcp.server import Server
from mcp.types import TextContent, Tool

# MinerU API 配置
MINERU_API_BASE = "http://localhost:8000"

app = Server("mineru")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用的 MinerU 工具"""
    return [
        Tool(
            name="parse_pdf",
            description="Parse a PDF document and extract text, images, tables, and formulas",
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Path to the PDF file"
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["pipeline", "vlm-http-client", "hybrid-http-client", "vlm-auto-engine", "hybrid-auto-engine"],
                        "description": "Parsing backend to use",
                        "default": "hybrid-http-client"
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["ch", "en", "japan", "korean"],
                        "description": "Document language",
                        "default": "ch"
                    },
                    "formula_enable": {
                        "type": "boolean",
                        "description": "Enable formula recognition",
                        "default": True
                    },
                    "table_enable": {
                        "type": "boolean",
                        "description": "Enable table recognition",
                        "default": True
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        Tool(
            name="get_task_status",
            description="Get the status of a parsing task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID returned by parse_pdf"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="get_task_images",
            description="Get extracted images from a completed task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from parse_pdf"
                    }
                },
                "required": ["task_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """执行 MinerU 工具"""
    
    async with httpx.AsyncClient() as client:
        if name == "parse_pdf":
            # 读取 PDF 文件
            pdf_path = arguments["pdf_path"]
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()
            
            # 提交解析任务
            files = {"pdf_file": ("document.pdf", pdf_content, "application/pdf")}
            data = {
                "backend": arguments.get("backend", "hybrid-http-client"),
                "lang": arguments.get("lang", "ch"),
                "formula_enable": arguments.get("formula_enable", True),
                "table_enable": arguments.get("table_enable", True),
                "return_md": True
            }
            
            if "server_url" in arguments:
                data["server_url"] = arguments["server_url"]
            
            response = await client.post(
                f"{MINERU_API_BASE}/tasks",
                files=files,
                data=data
            )
            result = response.json()
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "get_task_status":
            task_id = arguments["task_id"]
            response = await client.get(f"{MINERU_API_BASE}/tasks/{task_id}")
            result = response.json()
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        elif name == "get_task_images":
            task_id = arguments["task_id"]
            response = await client.get(f"{MINERU_API_BASE}/tasks/{task_id}/images")
            result = response.json()

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
        
        else:
            raise ValueError(f"Unknown tool: {name}")

async def main():
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
```

### 3.2 使用 MCP 客户端调用

配置 MCP 客户端（如 Claude Desktop、Cline 等）：

```json
{
  "mcpServers": {
    "mineru": {
      "command": "python",
      "args": ["/path/to/mineru_mcp_server.py"],
      "env": {
        "MINERU_API_BASE": "http://localhost:8000"
      }
    }
  }
}
```

### 3.3 在容器中运行 MCP 服务器

修改 Docker Compose 添加 MCP 服务：

```yaml
services:
  mineru-mcp:
    image: mineru-rocm:latest
    container_name: mineru-mcp-strix
    restart: unless-stopped
    
    # 不需要 GPU，纯 API 转发
    environment:
      - MINERU_API_BASE=http://mineru-hybrid:8000
    
    volumes:
      - ./input:/input:ro
      - ./mineru_mcp_server.py:/app/mineru_mcp_server.py:ro
    
    # 暴露 MCP 端口（stdio 或 SSE）
    command: >
      /bin/bash -c "
        pip install mcp &&
        python /app/mineru_mcp_server.py
      "
    
    depends_on:
      - mineru-hybrid
```

## 4. 快速测试脚本

创建 `test_mineru_api.py`：

```python
#!/usr/bin/env python3
"""测试 MinerU API 调用"""

import httpx
import sys
import time
from pathlib import Path

API_BASE = "http://localhost:8000"

def submit_task(pdf_path: str, backend: str = "hybrid-http-client", server_url: str = None):
    """提交 PDF 解析任务"""
    
    with open(pdf_path, "rb") as f:
        files = {"pdf_file": (Path(pdf_path).name, f, "application/pdf")}
        data = {
            "backend": backend,
            "lang": "ch",
            "formula_enable": True,
            "table_enable": True,
            "return_md": True
        }
        if server_url:
            data["server_url"] = server_url
        
        response = httpx.post(f"{API_BASE}/parse", files=files, data=data)
        response.raise_for_status()
        return response.json()

def wait_for_completion(task_id: str, timeout: int = 300):
    """等待任务完成"""
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = httpx.get(f"{API_BASE}/tasks/{task_id}")
        result = response.json()
        
        status = result.get("status")
        print(f"Task {task_id}: {status}")
        
        if status == "completed":
            return result
        elif status == "failed":
            raise RuntimeError(f"Task failed: {result}")
        
        time.sleep(2)
    
    raise TimeoutError("Task did not complete in time")

def download_result(task_id: str, output_path: str):
    """下载解析结果"""
    
    response = httpx.get(f"{API_BASE}/tasks/{task_id}/result")
    
    with open(output_path, "wb") as f:
        f.write(response.content)
    
    print(f"Result saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_mineru_api.py <pdf_path> [backend] [server_url]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    backend = sys.argv[2] if len(sys.argv) > 2 else "hybrid-http-client"
    server_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    print(f"Submitting task: {pdf_path}")
    print(f"Backend: {backend}")
    if server_url:
        print(f"Server URL: {server_url}")
    
    # 提交任务
    submit_result = submit_task(pdf_path, backend, server_url)
    task_id = submit_result["task_id"]
    print(f"Task ID: {task_id}")
    
    # 等待完成
    print("Waiting for completion...")
    final_result = wait_for_completion(task_id)
    
    # 下载结果
    output_zip = f"result_{task_id}.zip"
    download_result(task_id, output_zip)
    
    # 解压查看
    import zipfile
    with zipfile.ZipFile(output_zip, 'r') as zf:
        zf.extractall(f"output_{task_id}")
        print(f"Extracted files: {zf.namelist()}")
```

## 5. 总结

| 需求 | 解决方案 |
|------|---------|
| **直接 HTTP 调用** | 使用 FastAPI 端点 `http://localhost:8000` |
| **命令行调用** | `docker exec` 进入容器执行 `mineru` 命令 |
| **Web 界面** | 启动 Gradio 服务，访问 `http://localhost:7860` |
| **MCP 支持** | 需要自己实现 MCP 服务器包装 MinerU API |
| **批量处理** | 使用 `test_mineru_api.py` 脚本批量提交任务 |

## 6. 注意事项

1. **服务启动时间**：容器启动后需要 30-60 秒下载模型，首次调用可能较慢
2. **GPU 显存**：确保 Strix Halo 的显存足够（方案 A 需要 2-4GB，方案 B 需要 16GB+）
3. **网络连接**：方案 A 需要能访问第三方 VLM API
4. **文件权限**：确保挂载的目录有正确的读写权限

## 8. 安全与认证

### 8.1 原生 API 安全状态

**MinerU 原生 FastAPI 服务没有内置认证机制**，默认情况下：
- 端口 8000 (FastAPI) - 无认证，任何能访问该端口的客户端都可以调用
- 端口 7860 (Gradio) - 无认证，公开访问

### 8.2 推荐的认证方案

#### 方案 A：Nginx 反向代理 + Bearer Token（推荐）

**创建 `nginx_auth.conf`：**
```nginx
server {
    listen 8080;
    
    # Bearer Token 验证
    set $expected_token "your-secret-token-here";
    
    if ($http_authorization != "Bearer $expected_token") {
        return 401 "Unauthorized";
    }
    
    location / {
        proxy_pass http://mineru-hybrid:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

**修改 Docker Compose：**
```yaml
services:
  mineru-hybrid:
    # ... 原有配置 ...
    # 移除端口映射，只允许内部访问
    # ports:
    #   - "8000:8000"
    
  nginx-auth:
    image: nginx:alpine
    container_name: mineru-nginx-auth
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./nginx_auth.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - mineru-hybrid
    networks:
      - mineru-network

networks:
  mineru-network:
    driver: bridge
```

**带认证的 API 调用：**
```bash
# 使用 Bearer Token 调用
curl -X POST "http://localhost:8080/parse" \
  -H "Authorization: Bearer your-secret-token-here" \
  -F "pdf_file=@document.pdf" \
  -F "backend=hybrid-http-client"
```

#### 方案 B：API 密钥查询参数（简单方案）

如果不想使用 Nginx，可以在应用层添加简单的 API Key 验证：

**创建 `mineru_auth_wrapper.py`：**
```python
#!/usr/bin/env python3
"""MinerU API 认证包装器"""

import os
import hmac
import hashlib
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx

app = FastAPI()
security = HTTPBearer()

# 从环境变量读取 API Key
API_KEY = os.getenv("MINERU_API_KEY", "default-key-change-in-production")
MINERU_BASE_URL = os.getenv("MINERU_API_BASE", "http://mineru-hybrid:8000")

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证 Bearer Token"""
    token = credentials.credentials
    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token

@app.post("/parse")
async def parse_pdf(
    token: str = Depends(verify_token),
    # 其他参数透传给 MinerU
):
    """代理到 MinerU 的解析接口"""
    async with httpx.AsyncClient() as client:
        # 转发请求到 MinerU
        response = await client.post(f"{MINERU_BASE_URL}/parse", ...)
        return response.json()

# 其他端点...
```

**Docker Compose 添加认证服务：**
```yaml
  mineru-auth:
    image: python:3.10-slim
    container_name: mineru-auth
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - MINERU_API_KEY=${MINERU_API_KEY:-your-secret-key}
      - MINERU_API_BASE=http://mineru-hybrid:8000
    volumes:
      - ./mineru_auth_wrapper.py:/app/main.py:ro
    command: >
      /bin/bash -c "
        pip install fastapi uvicorn httpx python-multipart &&
        uvicorn main:app --host 0.0.0.0 --port 8080
      "
    depends_on:
      - mineru-hybrid
    networks:
      - mineru-network
```

#### 方案 C：网络隔离（最简单）

如果 MinerU 只在内部网络使用，可以通过 Docker 网络隔离：

```yaml
services:
  mineru-hybrid:
    # ... 原有配置 ...
    # 不暴露端口到宿主机
    # 只允许特定服务访问
    networks:
      - internal

  your-app:
    image: your-app:latest
    networks:
      - internal
    # 你的应用可以通过 http://mineru-hybrid:8000 访问

networks:
  internal:
    internal: true  # 禁止外部访问
```

### 8.3 安全建议

| 场景 | 推荐方案 | 说明 |
|------|---------|------|
| 生产环境，公网访问 | 方案 A (Nginx + Bearer) | 最安全的标准做法 |
| 内部网络，简单部署 | 方案 C (网络隔离) | 简单有效 |
| 需要复杂权限控制 | 方案 B (自定义包装器) | 可扩展性强 |
| 开发/测试环境 | 无认证 | 方便调试 |

### 8.4 环境变量配置

创建 `.env` 文件管理密钥：

```bash
# .env
MINERU_API_KEY=sk-mineru-2024-your-secure-key-here
MINERU_VLM_API_KEY=your-vlm-api-key
MINERU_VLM_BASE_URL=https://api.openai.com/v1
MINERU_VLM_MODEL=gpt-4o
```

**注意：**
- 永远不要将 `.env` 文件提交到 Git
- 生产环境使用更安全的密钥管理方式（如 Docker Secrets、Kubernetes Secrets）
- 定期轮换 API Key
