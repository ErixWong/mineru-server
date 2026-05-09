# MCP Server 评估与比较：MarkItDown vs MineRU

> 评估日期：2026-05-06

## 1. 项目概览

| 维度 | MarkItDown (markitdown-server) | MineRU MCP |
|------|-------------------------------|------------|
| **定位** | 文件转 Markdown 的全功能服务端 | PDF 解析的 MCP 代理层 |
| **MCP 框架** | FastMCP (`mcp>=1.8.0`) | FastMCP (`mcp>=1.0.0`) |
| **架构模式** | **单体服务**（内含解析引擎） | **瘦代理/网关**（转发至 MinerU FastAPI） |
| **代码量** | ~2000 行 (server 包) | ~2850 行 (mcp 模块) |
| **版本** | 0.1.0 | 0.1.3 |

## 2. 架构对比

### MarkItDown-Server：单体架构

```
Client → Starlette (统一入口)
           ├─ FastAPI (/api)      → REST API (12+ 端点)
           ├─ MCP SSE (/mcp/sse)  → SseServerTransport
           └─ MCP HTTP (/mcp)     → StreamableHTTPSessionManager
                                      ↓
                              FastMCP (5 tools)
                                      ↓
                           TaskProcessor → MarkItDown 库 (直接调用)
                                      ↓
                           TaskStore (SQLite 持久化)
```

**特点**：MCP server **内置**解析能力，直接调用 MarkItDown 库完成转换，结果存入 SQLite。

### MineRU MCP：代理/网关架构

```
Client → FastMCP Server (stdio / streamable-http)
                    ↓ (httpx 异步 HTTP)
           MinerU FastAPI (localhost:8000)
                    ↓
           PDF 解析后端 (pipeline / VLM / hybrid)
```

**特点**：MCP server **不含解析能力**，所有工作通过 HTTP 委托给 MinerU FastAPI 后端。

## 3. 功能对比

### 3.1 MCP Tools

| 能力 | MarkItDown | MineRU |
|------|-----------|--------|
| **工具数量** | 5 | 8 |
| **同步解析** | ❌ (全是异步任务) | ✅ `parse_pdf` |
| **异步任务提交** | ✅ `submit_conversion_task` | ✅ `submit_task` |
| **任务查询** | ✅ `get_task` | ✅ `get_task_status` + `get_task_result` |
| **任务取消** | ✅ `cancel_task` | ❌ |
| **任务列表** | ✅ `list_tasks` | ❌ |
| **格式列表** | ✅ `get_supported_formats` | ✅ `list_backends` |
| **Markdown 提取** | (包含在 get_task 中) | ✅ `extract_markdown` (便捷方法) |
| **图片提取** | ❌ | ✅ `get_images` (Base64) |
| **健康检查** | ❌ (REST 有 /health) | ✅ `health_check` |
| **页码范围** | ❌ | ✅ `start_page_id` / `end_page_id` |
| **语言选择** | ❌ | ✅ `lang` 参数 |
| **公式/表格** | ❌ | ✅ `formula_enable` / `table_enable` |
| **后端选择** | ❌ | ✅ `backend` 参数 (pipeline/VLM/hybrid) |

### 3.2 Transport

| Transport | MarkItDown | MineRU |
|-----------|-----------|--------|
| **STDIO** | ❌ | ✅ (默认模式) |
| **SSE** | ✅ `/mcp/sse` | ❌ |
| **Streamable HTTP** | ✅ `/mcp` (stateless) | ✅ `streamable-http` 模式 |
| **SSE 任务通知** | ✅ `/mcp/tasks/events` | ❌ |

### 3.3 REST API

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **REST API** | ✅ 12+ 端点 (FastAPI) | ❌ (MCP 专属) |
| **文件上传 (Base64)** | ✅ | ❌ |
| **文件上传 (Multipart)** | ✅ | ❌ |
| **文件上传 (本地路径)** | ✅ | ✅ |
| **Docker Compose** | ✅ | ✅ |

### 3.4 安全性

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **Bearer Token Auth** | ✅ (REST + MCP) | ✅ (已实现但未接入) |
| **Admin Token** | ✅ (管理端点) | ❌ |
| **DNS Rebinding 防护** | ✅ | ❌ |
| **路径穿越防护** | ❌ | ✅ (`validate_file_path` 9 项检查) |
| **文件扩展名白名单** | ❌ | ✅ |
| **文件大小限制** | ✅ (100MB, 中间件) | ✅ (500MB, 验证层) |
| **速率限制** | ✅ (管理端点) | ✅ (滑动窗口, 已实现但未接入) |
| **并发控制** | ✅ (任务队列 FIFO/Ratio) | ✅ (信号量, 已实现但未接入) |
| **敏感信息脱敏** | ❌ | ✅ (自动去除 api_key/token 等) |
| **错误信息路径遮蔽** | ❌ | ✅ |
| **符号链接策略** | ❌ | ✅ |

### 3.5 错误处理

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **结构化错误码** | ❌ (简单字符串) | ✅ (17 个枚举错误码) |
| **错误分类** | 文件/队列/处理 | 文件/任务/验证/API/认证/内部 |
| **错误返回方式** | HTTP 异常 / dict | dict (保持 MCP 协议兼容) |
| **异常映射** | ❌ | ✅ `from_exception()` 自动映射 |
| **部分成功** | ✅ (PDF 逐页处理, 跳过错误页) | ❌ |

### 3.6 任务管理

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **任务持久化** | ✅ SQLite | ❌ (无状态代理) |
| **调度策略** | FIFO / Ratio (大小文件分流) | ❌ |
| **进度追踪** | ✅ (progress %) | ❌ (委托后端) |
| **SSE 实时通知** | ✅ pub/sub | ❌ |
| **任务超时** | ❌ | ✅ (600s, 配置化) |

### 3.7 OCR 支持

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **OCR 引擎** | LLM Vision API (OpenAI 兼容) | MinerU 内置 (pipeline/VLM) |
| **逐页 OCR** | ✅ (PyMuPDF 提取 + LLM) | ✅ (后端处理) |
| **配置化** | ✅ (API Key/Base/Model) | ✅ (VLM 配置) |

## 4. 测试对比

| 特性 | MarkItDown | MineRU |
|------|-----------|--------|
| **单元测试** | ✅ (任务队列为主) | ✅ (验证/错误/配置/客户端) |
| **集成测试** | ✅ (ASGI 端到端) | ✅ (需要运行中 MinerU 实例) |
| **JS 端测试** | ✅ (MCP 协议级) | ❌ |
| **Mock 测试** | ✅ (部分) | ❌ |
| **Auth 测试** | ❌ | ❌ |
| **并发测试** | ✅ (队列策略) | ❌ |
| **测试覆盖面** | 中等 | 较低 |

## 5. 代码质量评估

### MarkItDown-Server

| 优点 | 问题 |
|------|------|
| 架构清晰, 层次分明 | 文件校验较弱, 无路径穿越防护 |
| SQLite 持久化, 支持任务恢复 | 无结构化错误码体系 |
| 调度策略灵活 (FIFO/Ratio) | 密钥信息可能泄露到日志 |
| SSE 实时通知 | MCP SDK 版本锁定过紧 |
| 统一 Starlette 入口, 可独立关闭 API/MCP | 无 STDIO 模式 |
| Docker Compose 一键部署 | |

### MineRU MCP

| 优点 | 问题 |
|------|------|
| 安全体系完善 (9 项文件验证) | **Auth/并发模块已实现但未接入** (关键问题) |
| 结构化错误处理 (17 个错误码) | 无状态, 任务全靠后端管理 |
| 敏感信息自动脱敏 | tests/__init__.py 复制了 test_mcp.py (bug) |
| All-in-One Docker 部署 | 无任务取消/列表能力 |
| 双模式 Transport (stdio + HTTP) | MCP SDK 版本偏旧 (>=1.0.0 vs >=1.8.0) |
| PDF 特化参数丰富 | 缺少 REST API 通道 |
| 单例模式, 代码模块化好 | |

## 6. 关键差距与建议

### MineRU 需要优先解决的问题

1. **🔴 接入 Auth 和并发控制**：`auth.py` 和 `concurrency.py` 已实现但未在 `server.py` 的 tool handler 中使用，形同虚设
2. **🔴 修复 tests/__init__.py**：该文件错误地复制了 test_mcp.py 的全部内容
3. **🟡 升级 MCP SDK**：从 `>=1.0.0` 升级到 `>=1.8.0`，以获得最新的 StreamableHTTP 稳定版
4. **🟡 添加任务取消/列表工具**：MarkItDown 已有这两个能力
5. **🟡 增加 SSE Transport**：部分 MCP 客户端仍依赖 SSE 模式

### 可从 MarkItDown 借鉴的设计

| 设计 | 描述 | 适用性 |
|------|------|--------|
| **统一 Starlette 入口** | 将 REST API 和 MCP 挂载到同一个 Starlette app | ⭐⭐⭐ 高 — MineRU 可以在 MCP 层旁挂载 REST API |
| **SQLite 任务持久化** | 任务状态持久存储, 支持服务重启恢复 | ⭐⭐ 中 — MineRU 的任务在后端管理, 代理层可缓存状态 |
| **FIFO/Ratio 调度策略** | 按文件大小分流, 小文件优先 | ⭐⭐ 中 — 可用于代理层请求调度 |
| **SSE 实时通知** | 任务进度通过 SSE 推送到客户端 | ⭐⭐⭐ 高 — 适合长时间 PDF 解析场景 |
| **逐页处理 + 部分成功** | 失败页面跳过继续处理 | ⭐ 低 — MinerU 后端已有类似机制 |
| **DNS Rebinding 防护** | 检测 Origin header 防止 DNS 重绑定攻击 | ⭐⭐ 中 — HTTP 模式下的安全加固 |

### MarkItDown 可借鉴 MineRU 的设计

| 设计 | 描述 | 适用性 |
|------|------|--------|
| **路径穿越防护** | 9 项文件验证检查 | ⭐⭐⭐ 高 — MarkItDown 完全缺失 |
| **结构化错误码** | 17 个枚举错误码 + 异常自动映射 | ⭐⭐⭐ 高 — 统一错误处理 |
| **敏感信息脱敏** | 自动移除 api_key/token 等 | ⭐⭐⭐ 高 — 安全必须 |
| **STDIO Transport** | 支持桌面客户端 (Claude Desktop) | ⭐⭐ 中 — 扩大客户端覆盖面 |
| **PDF 专化参数** | 页码范围/语言/公式/表格开关 | ⭐ 低 — 非通用 Markdown 转换需求 |

## 7. 综合评分

| 维度 | MarkItDown-Server | MineRU MCP | 说明 |
|------|:-:|:-:|------|
| **架构设计** | 8/10 | 7/10 | MarkItDown 单体更自洽；MineRU 代理模式有额外运维开销 |
| **功能丰富度** | 7/10 | 8/10 | MineRU 工具更多、PDF 特化参数更全；MarkItDown 有任务管理 |
| **安全性** | 5/10 | 7/10 | MineRU 验证/脱敏体系更完善, 但关键模块未接入 |
| **错误处理** | 6/10 | 9/10 | MineRU 的 17 错误码体系远优于 MarkItDown |
| **生产就绪** | 8/10 | 6/10 | MarkItDown 持久化+调度+SSE 更适合生产；MineRU 有未接入模块 |
| **可扩展性** | 7/10 | 8/10 | MineRU 的后端解耦支持多种解析引擎 |
| **测试覆盖** | 6/10 | 5/10 | 两者测试都偏少 |
| **代码质量** | 7/10 | 7/10 | 各有优劣 |

### 综合评价

- **MarkItDown-Server**：更适合作为**独立生产服务**部署，有完整的任务生命周期管理（提交→队列→处理→持久化→通知），开箱即用
- **MineRU MCP**：更适合作为**AI Agent 工具**嵌入，PDF 解析能力更强（多后端、VLM、页码控制），安全基础设施更完善但需要补齐"最后一公里"（接入已实现的模块）

两者是**互补关系**而非竞争关系：MarkItDown 做通用文件格式转换，MineRU 做深度 PDF 结构化解析。
