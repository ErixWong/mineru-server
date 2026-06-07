# MinerU 配置传递路径文档

> Historical note
>
> 本文档记录的是配置流设计与多轮实现演进，部分代码路径仍保留旧包名引用。
> 当前项目中的 MCP Server Python 包实际路径为 `mcp-server/src/mineru_mcp/`，不是 `src/mineru/mcp/`。

## 概述

本文档详细记录 MinerU MCP Server 和 MinerU FastAPI 的配置传递路径，帮助理解环境变量如何从 `.env` 文件传递到最终的 VLM API 调用。

---

## 变更记录：基于官方代码的修改

> ⚠️ **重要说明**：以下功能是在 MinerU 官方代码基础上新增的修改，用于支持 MCP Server 和环境变量直接读取。

### 修改 1：`vlm_analyze.py` - VLM 配置环境变量支持

**官方代码问题**：
- GitHub Issue #3994 确认官方存在 bug：`server_headers` 参数从未传递给 `MinerUClient`
- 官方文档承诺支持 `MINERU_VLM_API_KEY` 等环境变量，但代码未实现

**我们的修改** ([`vlm_analyze.py:80-130`](src/mineru/backend/vlm/vlm_analyze.py:80))：
```python
# 新增：支持从环境变量直接读取 VLM 配置
if backend == "http-client":
    # Handle API key for server_headers
    api_key = os.getenv("MINERU_VLM_API_KEY")  # 新增环境变量读取
    if api_key:
        server_headers = {"Authorization": f"Bearer {api_key}"}
    else:
        # 备选：从配置文件读取
        llm_aided_config = get_llm_aided_config()
        ...
    
    # Handle model_name
    model_name = os.getenv("MINERU_VLM_MODEL")  # 新增环境变量读取
    ...
    
    # Handle max_concurrency
    max_concurrency_str = os.getenv("MINERU_VLM_MAX_CONCURRENCY")  # 新增环境变量读取
    ...
```

**新增环境变量**：
- `MINERU_VLM_API_KEY` - VLM API 认证密钥（修复官方 bug）
- `MINERU_VLM_MODEL` - VLM 模型名称
- `MINERU_VLM_MAX_CONCURRENCY` - 最大并发请求数

### 修改 2：`llm_aided.py` - Title LLM 配置环境变量支持

**官方代码问题**：
- 官方代码硬编码从配置字典读取，不支持环境变量
- 必须通过 `mineru.json` 配置文件传递配置

**官方代码** ([`llm_aided.py:155-158`](src/mineru/utils/llm_aided.py:155))：
```python
# 官方代码：只从配置字典读取
client = OpenAI(
    api_key=title_aided_config["api_key"],      # 硬编码，不支持环境变量
    base_url=title_aided_config["base_url"],    # 硬编码，不支持环境变量
)
```

**我们的修改** ([`llm_aided.py:156-178`](src/mineru/utils/llm_aided.py:156))：
```python
# 修改后：优先从环境变量读取
api_key = os.getenv("MINERU_TITLE_API_KEY") or title_aided_config.get("api_key")
base_url = os.getenv("MINERU_TITLE_BASE_URL") or title_aided_config.get("base_url")
model = os.getenv("MINERU_TITLE_MODEL") or title_aided_config.get("model")

client = OpenAI(
    api_key=api_key,      # 优先从环境变量获取
    base_url=base_url,    # 优先从环境变量获取
)
```

**新增环境变量**：
- `MINERU_TITLE_API_KEY` - Title LLM API 密钥
- `MINERU_TITLE_BASE_URL` - Title LLM API 地址
- `MINERU_TITLE_MODEL` - Title LLM 模型名称

### 修改 3：移除 `sync_to_mineru_config()` 函数

**变更说明**：
- 原设计：`get_config()` 自动调用 `sync_to_mineru_config()` 将环境变量同步到 `mineru.json`
- 新设计：完全移除 `sync_to_mineru_config()` 函数，因为 `vlm_analyze.py` 和 `llm_aided.py` 现在直接从环境变量读取

**移除的代码** ([`config.py`](mcp-server/src/mineru_mcp/config.py))：
- 删除 `sync_to_mineru_config()` 方法（约 75 行代码）
- 删除 `MINERU_CONFIG_DIR` 和 `MINERU_CONFIG_FILE` 常量
- 删除 `import json` 和 `from pathlib import Path`
- 删除 `has_vlm_config()` 和 `has_title_config()` 方法（不再使用）

**修改后** ([`config.py`](mcp-server/src/mineru_mcp/config.py))：
```python
def get_config() -> MCPConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = MCPConfig.from_env()
        # Note: sync_to_mineru_config() has been removed.
        # vlm_analyze.py and llm_aided.py now read from environment variables directly.
    return _config
```

**配置优先级**（统一）：
```
环境变量 > 配置文件 (mineru.json) > kwargs 参数
```

**结论**：不再需要 `mineru.json` 配置文件，所有配置通过环境变量传递。

---

## 1. 配置传递流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           .env 文件                                          │
│  MINERU_VLM_API_KEY=sk-xxx                                                  │
│  MINERU_VLM_BASE_URL=https://api.xxx/v1                                    │
│  MINERU_VLM_MODEL=gpt-4o                                                    │
│  MINERU_VLM_MAX_CONCURRENCY=1                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ load_dotenv()
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        环境变量 (os.environ)                                  │
│  os.getenv("MINERU_VLM_API_KEY") → "sk-xxx"                                 │
│  os.getenv("MINERU_VLM_BASE_URL") → "https://api.xxx/v1"                   │
│  os.getenv("MINERU_VLM_MODEL") → "gpt-4o"                                   │
│  os.getenv("MINERU_VLM_MAX_CONCURRENCY") → "1"                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────┐
│      MCP Server (MCPConfig)      │   │    MinerU FastAPI (vlm_analyze)   │
│                                  │   │                                  │
│  mineru/mcp/config.py:           │   │  mineru/backend/vlm/vlm_analyze.py│
│  - vlm_api_key                   │   │  - MINERU_VLM_API_KEY → headers   │
│  - vlm_base_url                  │   │  - MINERU_VLM_MODEL → model_name  │
│  - vlm_model                     │   │  - MINERU_VLM_MAX_CONCURRENCY     │
│                                  │   │                                  │
│  用于:                           │   │  用于:                            │
│  - MinerUClient 调用参数         │   │  - MinerUClient 初始化参数        │
│                                  │   │  - 直接读取，无需配置文件         │
└──────────────────────────────────┘   └──────────────────────────────────┘
                    │                               │
                    │ server_url 参数               │ 直接读取环境变量
                    ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MinerU FastAPI (fast_api.py)                          │
│                                                                              │
│  接收参数:                                                                    │
│  - server_url (来自 MCP Server 或 API 请求)                                  │
│  - backend (来自 MCP Server 或 API 请求)                                     │
│                                                                              │
│  传递给: run_parse_job → aio_do_parse → vlm_doc_analyze                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ kwargs 传递
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        vlm_analyze.py (ModelSingleton)                       │
│                                                                              │
│  参数来源优先级:                                                              │
│  1. 环境变量 (最高优先级)                                                     │
│  2. 配置文件 (mineru.json)                                                   │
│  3. kwargs 参数                                                              │
│                                                                              │
│  最终传递给 MinerUClient:                                                    │
│  - server_url                                                                │
│  - model_name                                                                │
│  - server_headers (从 API_KEY 构建)                                          │
│  - max_concurrency                                                           │
│  - http_timeout                                                              │
│  - max_retries                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ MinerUClient 初始化
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MinerUClient (mineru_vl_utils)                        │
│                                                                              │
│  HTTP Client 后端:                                                           │
│  - 使用 server_url 连接 VLM API                                              │
│  - 使用 server_headers 进行认证                                              │
│  - 使用 model_name 指定模型                                                  │
│  - 使用 max_concurrency 控制并发                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 环境变量分类

### 2.1 MCP Server 专用环境变量

这些环境变量由 MCP Server 的 `MCPConfig` 读取，用于控制 MCP Server 行为和 MinerU API 调用：

| 环境变量 | 读取位置 | 用途 |
|----------|----------|------|
| `MINERU_API_BASE` | `mcp-server/src/mineru_mcp/config.py` | MinerU FastAPI 地址 |
| `MINERU_DEFAULT_BACKEND` | `mcp-server/src/mineru_mcp/config.py` | 默认解析后端 |
| `MCP_SERVER_NAME` | `mcp-server/src/mineru_mcp/config.py` | MCP Server 名称 |
| `MCP_SERVER_MODE` | `mcp-server/src/mineru_mcp/config.py` | Server 模式 (stdio/http) |
| `MCP_HTTP_HOST` | `mcp-server/src/mineru_mcp/config.py` | HTTP 主机地址 |
| `MCP_HTTP_PORT` | `mcp-server/src/mineru_mcp/config.py` | HTTP 端口 |
| `MCP_HTTP_AUTH_TOKEN` | `mcp-server/src/mineru_mcp/config.py` | HTTP 认证令牌 |
| `MCP_LOG_LEVEL` | `mcp-server/src/mineru_mcp/config.py` | 日志级别 |

### 2.2 VLM 配置环境变量

这些环境变量用于配置 VLM API 连接，**直接在 `vlm_analyze.py` 读取**：

| 环境变量 | 读取位置 | 用途 | 对应 MinerUClient 参数 |
|----------|----------|------|------------------------|
| `MINERU_VLM_API_KEY` | [`vlm_analyze.py:92`](src/mineru/backend/vlm/vlm_analyze.py:92) | VLM API 认证密钥 | 构建 `server_headers` |
| `MINERU_VLM_BASE_URL` | `mcp-server/src/mineru_mcp/config.py` | VLM API 服务地址 | `server_url` |
| `MINERU_VLM_MODEL` | [`vlm_analyze.py:109`](src/mineru/backend/vlm/vlm_analyze.py:109) | VLM 模型名称 | `model_name` |
| `MINERU_VLM_MAX_CONCURRENCY` | [`vlm_analyze.py:122`](src/mineru/backend/vlm/vlm_analyze.py:122) | 最大并发请求数 | `max_concurrency` |

### 2.3 VLM 功能开关环境变量

这些环境变量由 MinerU 内部处理逻辑读取：

| 环境变量 | 读取位置 | 用途 |
|----------|----------|------|
| `MINERU_VLM_FORMULA_ENABLE` | [`common.py:674`](src/mineru/cli/common.py:674) | 公式识别开关 |
| `MINERU_VLM_TABLE_ENABLE` | [`common.py:675`](src/mineru/cli/common.py:675) | 表格识别开关 |

### 2.4 Title 优化 LLM 环境变量

这些环境变量用于标题层级优化，**现在可以直接从环境变量读取**（已修改 `llm_aided.py`）：

| 环境变量 | 读取位置 | 用途 |
|----------|----------|------|
| `MINERU_TITLE_API_KEY` | [`llm_aided.py:156`](src/mineru/utils/llm_aided.py:156) | Title LLM API 密钥 |
| `MINERU_TITLE_BASE_URL` | [`llm_aided.py:157`](src/mineru/utils/llm_aided.py:157) | Title LLM API 地址 |
| `MINERU_TITLE_MODEL` | [`llm_aided.py:158`](src/mineru/utils/llm_aided.py:158) | Title LLM 模型名称 |

> ✅ **已修改**：`llm_aided.py` 现在支持从环境变量直接读取配置！
>
> 配置优先级：**环境变量 > 配置文件 (mineru.json)**
>
> - 设置 `MINERU_TITLE_API_KEY`、`MINERU_TITLE_BASE_URL`、`MINERU_TITLE_MODEL` 环境变量后，无需配置 `mineru.json`

---

## 3. 详细传递路径

### 3.1 MINERU_VLM_API_KEY 传递路径

```
.env 文件
    │
    │ MINERU_VLM_API_KEY=sk-xxx
    │
    ▼
load_dotenv() [cli.py:78]
    │
    │ os.environ["MINERU_VLM_API_KEY"] = "sk-xxx"
    │
    ▼
vlm_analyze.py:92 [直接读取]
    │
    │ api_key = os.getenv("MINERU_VLM_API_KEY")
    │ server_headers = {"Authorization": f"Bearer {api_key}"}
    │
    ▼
MinerUClient 初始化 [vlm_analyze.py:278]
    │
    │ predictor = MinerUClient(server_headers=server_headers, ...)
    │
    ▼
HTTP API 调用
    │
    │ Headers: Authorization: Bearer sk-xxx
    │
    ▼
VLM API Server
```

### 3.2 MINERU_VLM_BASE_URL 传递路径

```
.env 文件
    │
    │ MINERU_VLM_BASE_URL=https://api.xxx/v1
    │
    ▼
load_dotenv() [cli.py:78]
    │
    │ os.environ["MINERU_VLM_BASE_URL"] = "https://api.xxx/v1"
    │
    ▼
MCPConfig.from_env() [config.py:76]
    │
    │ vlm_base_url = os.getenv("MINERU_VLM_BASE_URL")
    │
    ▼
MCPConfig.get_vlm_server_url() [config.py:100-106]
    │
    │ return self.vlm_base_url
    │
    ▼
MCP Server submit path [mcp-server/src/mineru_mcp/server.py]
    │
    │ effective_server_url = config.get_vlm_server_url()
    │
    ▼
create_task_from_file() / REST API task submission [mcp-server/src/mineru_mcp/server.py, api.py]
    │
    │ server_url = effective_server_url
    │
    ▼
MinerU FastAPI [fast_api.py:854]
    │
    │ server_url=request_options.server_url
    │
    ▼
run_parse_job() [fast_api.py:961]
    │
    │ server_url=request_options.server_url
    │
    ▼
aio_do_parse() [common.py:774]
    │
    │ server_url=server_url
    │
    ▼
vlm_doc_analyze() [vlm_analyze.py:456-460]
    │
    │ predictor = ModelSingleton().get_model(..., server_url=server_url, ...)
    │
    ▼
MinerUClient 初始化 [vlm_analyze.py:273]
    │
    │ predictor = MinerUClient(server_url=server_url, ...)
    │
    ▼
HTTP API 调用
```

### 3.3 MINERU_VLM_MODEL 传递路径

```
.env 文件
    │
    │ MINERU_VLM_MODEL=gpt-4o
    │
    ▼
load_dotenv() [cli.py:78]
    │
    │ os.environ["MINERU_VLM_MODEL"] = "gpt-4o"
    │
    ▼
vlm_analyze.py:109 [直接读取]
    │
    │ model_name = os.getenv("MINERU_VLM_MODEL")
    │
    ▼
MinerUClient 初始化 [vlm_analyze.py:274]
    │
    │ predictor = MinerUClient(model_name=model_name, ...)
    │
    ▼
HTTP API 调用
    │
    │ 指定 VLM 模型名称
    │
    ▼
VLM API Server
```

### 3.4 MINERU_VLM_MAX_CONCURRENCY 传递路径

```
.env 文件
    │
    │ MINERU_VLM_MAX_CONCURRENCY=1
    │
    ▼
load_dotenv() [cli.py:78]
    │
    │ os.environ["MINERU_VLM_MAX_CONCURRENCY"] = "1"
    │
    ▼
vlm_analyze.py:122 [直接读取]
    │
    │ max_concurrency_str = os.getenv("MINERU_VLM_MAX_CONCURRENCY")
    │ max_concurrency = int(max_concurrency_str)
    │
    ▼
MinerUClient 初始化 [vlm_analyze.py:276]
    │
    │ predictor = MinerUClient(max_concurrency=max_concurrency, ...)
    │
    ▼
HTTP API 调用
    │
    │ 控制并发请求数量
    │
    ▼
VLM API Server
```

---

## 3.5 MINERU_TITLE_* 配置传递路径

> ✅ **已修改**：Title LLM 配置现在支持直接从环境变量读取！

Title LLM 用于优化文档标题层级，是**纯文本模型**（不是多模态 VLM）。其配置现在支持两种传递路径：

```
路径 1（推荐）：直接从环境变量读取（无需 mineru.json）

.env 文件
    │
    │ MINERU_TITLE_API_KEY=sk-xxx
    │ MINERU_TITLE_BASE_URL=https://api.xxx/v1
    │ MINERU_TITLE_MODEL=gpt-4
    │
    ▼
load_dotenv() [cli.py:78]
    │
    │ os.environ["MINERU_TITLE_API_KEY"] = "sk-xxx"
    │ os.environ["MINERU_TITLE_BASE_URL"] = "https://api.xxx/v1"
    │ os.environ["MINERU_TITLE_MODEL"] = "gpt-4"
    │
    ▼
hybrid_model_output_to_middle_json.py / model_output_to_middle_json.py
    │
    │ llm_aided_config = get_llm_aided_config()
    │ title_aided_config = llm_aided_config.get('title_aided', {})
    │ if title_aided_config.get('enable', False):
    │     llm_aided_title(pdf_info_list, title_aided_config)
    │
    ▼
llm_aided_title() [llm_aided.py:343]
    │
    │ # 调用 _request_title_levels()
    │
    ▼
_request_title_levels() [llm_aided.py:156-178]
    │
    │ # 优先从环境变量读取，备选从配置字典读取
    │ api_key = os.getenv("MINERU_TITLE_API_KEY") or title_aided_config.get("api_key")
    │ base_url = os.getenv("MINERU_TITLE_BASE_URL") or title_aided_config.get("base_url")
    │ model = os.getenv("MINERU_TITLE_MODEL") or title_aided_config.get("model")
    │
    │ client = OpenAI(
    │     api_key=api_key,      # 从环境变量或配置文件读取！
    │     base_url=base_url,    # 从环境变量或配置文件读取！
    │ )
    │
    │ response = client.chat.completions.create(
    │     model=model,          # 从环境变量或配置文件读取！
    │     ...
    │ )
    │
    ▼
OpenAI API 调用
    │
    │ 使用纯文本 LLM 优化标题层级
    │
    ▼
标题层级优化结果


```

### 3.5.1 Title LLM 配置现在支持环境变量（已修改）

**修改前**：`llm_aided.py` 硬编码从配置字典读取：

```python
# 原代码 llm_aided.py:155-158
client = OpenAI(
    api_key=title_aided_config["api_key"],      # 只从配置字典获取
    base_url=title_aided_config["base_url"],    # 只从配置字典获取
)
```

**修改后**：`llm_aided.py` 现在优先从环境变量读取：

```python
# 新代码 llm_aided.py:156-178
api_key = os.getenv("MINERU_TITLE_API_KEY") or title_aided_config.get("api_key")
base_url = os.getenv("MINERU_TITLE_BASE_URL") or title_aided_config.get("base_url")
model = os.getenv("MINERU_TITLE_MODEL") or title_aided_config.get("model")

client = OpenAI(
    api_key=api_key,      # 优先从环境变量获取
    base_url=base_url,    # 优先从环境变量获取
)
```

**配置优先级**：环境变量 > 配置文件 (mineru.json)

### 3.5.2 Title LLM 配置路径总结

**路径 1（推荐）：直接从环境变量读取**

| 步骤 | 文件 | 作用 |
|------|------|------|
| 1 | `.env` | 存储 `MINERU_TITLE_*` 环境变量 |
| 2 | `cli.py:78` | `load_dotenv()` 加载到 `os.environ` |
| 3 | `llm_aided.py:156-178` | `_request_title_levels()` 直接从环境变量读取 |

> ✅ **结论**：Title LLM 配置现在**可以直接从环境变量读取**，无需 `mineru.json`！

---

## 4. 配置优先级

### 4.1 vlm_analyze.py 中的优先级

```python
# 优先级: 环境变量 > 配置文件 > kwargs 参数

if backend == "http-client":
    # 1. 首先检查环境变量 (最高优先级)
    api_key = os.getenv("MINERU_VLM_API_KEY")
    if api_key:
        server_headers = {"Authorization": f"Bearer {api_key}"}
    else:
        # 2. 然后检查配置文件 (备选)
        llm_aided_config = get_llm_aided_config()
        if llm_aided_config:
            vlm_config = llm_aided_config.get("vlm", {})
            api_key = vlm_config.get("api_key")
            if api_key:
                server_headers = {"Authorization": f"Bearer {api_key}"}
    
    # 3. kwargs 参数已在之前提取，如果环境变量和配置文件都没有，则使用 kwargs
```

### 4.2 MCPConfig 中的优先级

```python
# MCPConfig 只读取环境变量，不读取配置文件
vlm_api_key = os.getenv("MINERU_VLM_API_KEY")  # 直接读取环境变量
vlm_base_url = os.getenv("MINERU_VLM_BASE_URL")
vlm_model = os.getenv("MINERU_VLM_MODEL")
```

---

## 5. 关键代码位置

### 5.1 .env 加载

**文件**: `mcp-server/src/mineru_mcp/cli.py`

```python
from dotenv import load_dotenv

env_path = Path.cwd() / ".env"
if env_path.exists():
    load_dotenv(env_path)  # 将 .env 文件内容加载到 os.environ
    logger.debug(f"Loaded .env from: {env_path}")
```

### 5.2 MCPConfig 环境变量读取

**文件**: `mcp-server/src/mineru_mcp/config.py`

```python
@classmethod
def from_env(cls) -> "MCPConfig":
    return cls(
        mineru_api_base=os.getenv("MINERU_API_BASE", "http://localhost:8000"),
        default_backend=os.getenv("MINERU_DEFAULT_BACKEND", DEFAULT_BACKEND),
        vlm_base_url=os.getenv("MINERU_VLM_BASE_URL"),
        vlm_api_key=os.getenv("MINERU_VLM_API_KEY"),
        vlm_model=os.getenv("MINERU_VLM_MODEL"),
        title_api_key=os.getenv("MINERU_TITLE_API_KEY"),
        title_base_url=os.getenv("MINERU_TITLE_BASE_URL"),
        title_model=os.getenv("MINERU_TITLE_MODEL"),
        server_name=os.getenv("MCP_SERVER_NAME", "MinerU MCP Server"),
        server_mode=os.getenv("MCP_SERVER_MODE", "stdio"),
        http_host=os.getenv("MCP_HTTP_HOST", "0.0.0.0"),
        http_port=int(os.getenv("MCP_HTTP_PORT", "8001")),
        http_auth_token=os.getenv("MCP_HTTP_AUTH_TOKEN"),
        log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
    )
```

### 5.3 vlm_analyze.py 环境变量读取

**文件**: [`src/mineru/backend/vlm/vlm_analyze.py`](src/mineru/backend/vlm/vlm_analyze.py:80-130)

```python
if backend == "http-client":
    # Handle API key for server_headers
    if server_url is not None and server_headers is None:
        api_key = os.getenv("MINERU_VLM_API_KEY")
        if api_key:
            server_headers = {"Authorization": f"Bearer {api_key}"}
            logger.info(f"Set server_headers from MINERU_VLM_API_KEY env var")
        else:
            llm_aided_config = get_llm_aided_config()
            if llm_aided_config is not None:
                vlm_config = llm_aided_config.get("vlm", {})
                api_key = vlm_config.get("api_key")
                if api_key:
                    server_headers = {"Authorization": f"Bearer {api_key}"}
    
    # Handle model_name
    if model_name is None:
        model_name = os.getenv("MINERU_VLM_MODEL")
        if model_name:
            logger.info(f"Set model_name from MINERU_VLM_MODEL env var: {model_name}")
        else:
            llm_aided_config = get_llm_aided_config()
            if llm_aided_config is not None:
                vlm_config = llm_aided_config.get("vlm", {})
                model_name = vlm_config.get("model")
    
    # Handle max_concurrency
    if max_concurrency is None:
        max_concurrency_str = os.getenv("MINERU_VLM_MAX_CONCURRENCY")
        if max_concurrency_str:
            max_concurrency = int(max_concurrency_str)
            logger.info(f"Set max_concurrency from MINERU_VLM_MAX_CONCURRENCY env var: {max_concurrency}")
        else:
            max_concurrency = 100  # 默认值
```

### 5.4 MinerUClient 参数传递

**文件**: [`src/mineru/backend/vlm/vlm_analyze.py`](src/mineru/backend/vlm/vlm_analyze.py:266-281)

```python
predictor = MinerUClient(
    backend=backend,
    model=model,
    processor=processor,
    lmdeploy_engine=lmdeploy_engine,
    vllm_llm=vllm_llm,
    vllm_async_llm=vllm_async_llm,
    server_url=server_url,
    model_name=model_name,  # VLM model name for http-client backend
    batch_size=batch_size,
    max_concurrency=max_concurrency,
    http_timeout=http_timeout,
    server_headers=server_headers,
    max_retries=max_retries,
    retry_backoff_factor=retry_backoff_factor,
)
```

---

## 6. 重要结论

### 6.1 无需 mineru.json

**设置环境变量后，`vlm_analyze.py` 和 `llm_aided.py` 直接读取环境变量，无需配置 `mineru.json` 文件！**

配置读取优先级：
```
环境变量 > 配置文件 (mineru.json) > kwargs 参数
```

### 6.2 环境变量命名统一

所有 VLM 相关环境变量统一使用 `MINERU_VLM_*` 前缀：

- `MINERU_VLM_API_KEY`
- `MINERU_VLM_BASE_URL`
- `MINERU_VLM_MODEL`
- `MINERU_VLM_MAX_CONCURRENCY`
- `MINERU_VLM_FORMULA_ENABLE`
- `MINERU_VLM_TABLE_ENABLE`

---

## 7. 参考

- `mcp-server/src/mineru_mcp/cli.py` - MCP Server CLI 入口，加载 .env
- `mcp-server/src/mineru_mcp/config.py` - MCP Server 配置类
- [`src/mineru/backend/vlm/vlm_analyze.py`](src/mineru/backend/vlm/vlm_analyze.py) - VLM 后端分析，直接读取环境变量
- [`src/mineru/cli/fast_api.py`](src/mineru/cli/fast_api.py) - MinerU FastAPI 服务
- [`src/mineru/cli/common.py`](src/mineru/cli/common.py) - 解析任务执行逻辑
- [`src/.env.example`](src/.env.example) - 环境变量示例文件
