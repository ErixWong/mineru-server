# MinerU MCP Server 改进总结

## 版本历史

| 版本 | 日期 | 改进内容 |
|------|------|----------|
| 0.1.0 | 2026-04-11 | 初始实现：MCP Server 集成到 MinerU 包 |
| 0.1.1 | 2026-04-11 | 添加输入验证和结构化错误处理 |
| 0.1.2 | 2026-04-11 | 添加 Bearer Token 认证模块 |
| 0.1.3 | 2026-04-12 | 添加并发控制模块 |

---

## 新增模块

### 1. 输入验证 (`validation.py`)

防止路径遍历攻击和无效输入：

```python
from mineru.mcp import validate_file_path, ValidationError

# 验证文件路径（防止路径遍历）
try:
    validated_path = validate_file_path(
        "/app/input/document.pdf",
        allowed_dirs=[Path("/app/input")],
        max_size=500 * 1024 * 1024,  # 500 MB
    )
except ValidationError as e:
    print(f"Error: {e.code} - {e.message}")
```

**验证功能**:
- `validate_file_path()` - 路径遍历检查、文件类型、大小限制
- `validate_task_id()` - 任务 ID 格式验证
- `validate_backend()` - 后端名称验证
- `validate_language()` - 语言代码验证
- `validate_page_range()` - 页码范围验证

---

### 2. 结构化错误处理 (`errors.py`)

统一的错误码和自动脱敏：

```python
from mineru.mcp import MCPError, from_exception, ErrorCode

# 预定义错误
error = file_not_found("/path/to/file.pdf")
print(error.to_dict())
# {"status": "error", "error_code": "FILE_NOT_FOUND", "error_message": "The specified file could not be found."}

# 自动转换异常
try:
    ...
except Exception as e:
    error = from_exception(e)
    return error.to_dict()  # 自动脱敏敏感信息
```

**错误码列表**:
| 类别 | 错误码 |
|------|--------|
| 文件 | `FILE_NOT_FOUND`, `PATH_TRAVERSAL`, `FILE_TOO_LARGE`, `INVALID_EXTENSION` |
| 任务 | `TASK_NOT_FOUND`, `TASK_FAILED`, `TASK_TIMEOUT`, `TASK_STILL_PROCESSING` |
| 验证 | `INVALID_BACKEND`, `INVALID_LANGUAGE`, `INVALID_PAGE_RANGE` |
| API | `MINERU_API_ERROR`, `MINERU_API_UNAVAILABLE` |
| 认证 | `AUTH_MISSING`, `AUTH_INVALID` |

---

### 3. Bearer Token 认证 (`auth.py`)

HTTP 模式下的 Token 认证：

```bash
# 生成安全 Token
python -m mineru.mcp.auth
# 输出: Generated auth token: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6

# 配置环境变量
export MCP_HTTP_AUTH_TOKEN=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6

# 客户端调用
curl -H "Authorization: Bearer a1b2c3d4e5f..." http://localhost:8001/mcp
```

**认证特性**:
- 时序安全比较（防止计时攻击）
- 支持 Bearer Token 格式
- 自动生成安全随机 Token

---

### 4. 并发控制 (`concurrency.py`)

限流和并发任务管理：

```python
from mineru.mcp import ConcurrencyManager, get_concurrency_manager

# 获取并发管理器
manager = get_concurrency_manager()

# 检查限流
if await manager.check_rate_limit():
    # 获取任务槽位
    if await manager.acquire_task_slot("task-123"):
        try:
            # 执行任务
            result = await parse_pdf(...)
        finally:
            # 释放槽位
            await manager.release_task_slot("task-123")

# 获取状态
status = manager.get_status()
# {"rate_limit": {"current_rate": 5, "max_per_minute": 60},
#  "tasks": {"active_count": 2, "max_concurrent": 5}}
```

**并发控制特性**:
- **RateLimiter**: 滑动窗口算法，60 requests/minute（默认）
- **ConcurrentTaskLimiter**: 信号量控制，5 concurrent tasks（默认）
- **超时清理**: 自动清理超过 600 秒的任务

---

## 环境变量配置

### 输入验证
```bash
MCP_ALLOWED_DIRS=/app/input,/app/data    # 允许的目录
MCP_ALLOW_SYMLINKS=false                  # 是否允许符号链接
```

### 认证
```bash
MCP_HTTP_AUTH_TOKEN=your-secret-token     # HTTP 认证 Token
```

### 并发控制
```bash
MCP_MAX_REQUESTS_PER_MINUTE=60            # 每分钟最大请求数
MCP_MAX_CONCURRENT_TASKS=5                # 最大并发任务数
MCP_TASK_TIMEOUT_SECONDS=600              # 任务超时时间（秒）
```

---

## Docker 资源限制

### 容器级别（Docker Compose）
```yaml
deploy:
  resources:
    limits:
      memory: 8G
      cpus: 4
    reservations:
      memory: 2G
      cpus: 1
```

### 应用级别（并发控制）
- Rate limiting: 60 requests/minute
- Concurrent tasks: 5 simultaneous
- Task timeout: 600 seconds

---

## 单元测试

运行测试：
```bash
cd src
pytest mineru/mcp/tests/test_mcp.py -v
```

测试覆盖：
- `TestValidation`: 验证函数测试
- `TestErrors`: 错误处理测试
- `TestConfig`: 配置管理测试
- `TestMinerUClient`: 客户端测试

---

## 文件结构

```
src/mineru/mcp/
├── __init__.py          # 模块导出
├── config.py            # 配置管理
├── validation.py        # 输入验证（新增）
├── errors.py            # 错误处理（新增）
├── auth.py              # 认证模块（新增）
├── concurrency.py       # 并发控制（新增）
├── mineru_client.py     # HTTP 客户端
├── server.py            # MCP Server
├── cli.py               # CLI 入口
├── entrypoint.py        # 容器启动
└── tests/
    ├── __init__.py
    └── test_mcp.py      # 单元测试（新增）
```

---

## 安全改进总结

| 改进 | 风险 | 解决方案 |
|------|------|----------|
| 路径遍历 | 读取任意文件 | `validate_file_path()` 检查路径是否在允许目录内 |
| 文件类型欺骗 | 上传恶意文件 | 扩展名白名单验证 |
| 资源耗尽 | DoS 攻击 | Rate limiting + Concurrent task limiter |
| 信息泄露 | 日志暴露敏感信息 | `MCPError` 自动脱敏路径和 Token |
| 未授权访问 | 任何人可调用 | Bearer Token 认证（可选） |

---

## 使用示例

### 基本使用
```python
from mineru.mcp import create_mcp_server, get_config

# 创建服务器
config = get_config()
server = create_mcp_server(config)

# 运行
server.run(transport="stdio")  # 或 "streamable-http"
```

### 带认证和并发控制
```python
import os
os.environ["MCP_HTTP_AUTH_TOKEN"] = "your-token"
os.environ["MCP_MAX_CONCURRENT_TASKS"] = "10"

from mineru.mcp import create_mcp_server, get_concurrency_manager

server = create_mcp_server()
manager = get_concurrency_manager()

# 在工具中使用
@mcp.tool()
async def parse_pdf(file_path: str):
    # 检查限流
    if not await manager.check_rate_limit():
        return {"error": "Rate limited"}
    
    # 获取槽位
    task_id = generate_task_id()
    if not await manager.acquire_task_slot(task_id):
        return {"error": "Too many concurrent tasks"}
    
    try:
        result = await do_parse(file_path)
        return result
    finally:
        await manager.release_task_slot(task_id)
```

---

*更新日期: 2026-04-12*