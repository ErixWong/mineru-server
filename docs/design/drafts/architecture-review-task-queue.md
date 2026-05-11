# 任务队列方案架构审视报告

**日期**: 2026-05-10
**审视角度**: 系统架构设计师
**状态**: Draft - 识别关键架构问题

---

## 1. 当前架构分析

### 1.1 All-in-One 模式架构

```
┌─────────────────────────────────────────────────────┐
│         Unified Starlette App (Port 8001)           │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │   /api/      │  │    /mcp/     │  │ /mineru_api│ │
│  │ (REST API)   │  │ (MCP SSE)    │  │(MinerU API)│ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│         │                 │                 │      │
│         └─────────────────┴─────────────────┘      │
│                           │                        │
│                  MinerUClient (HTTP)               │
│                           │                        │
│                           ▼                        │
│           MinerU Native FastAPI (内部挂载)          │
│           ├─ /file_parse (同步解析)                 │
│           ├─ /tasks (异步任务队列)                  │
│           ├─ /tasks/{id} (状态查询)                │
│           └─ SQLite 任务存储（MinerU 内部）         │
└─────────────────────────────────────────────────────┘
```

### 1.2 关键发现

**MinerU Native API 已有功能**：
- ✅ 异步任务队列 (`/tasks` 端点)
- ✅ 任务状态管理 (pending/processing/completed/failed)
- ✅ SQLite 任务存储（推测，待确认）
- ✅ 并发处理能力

**MCP Server 当前角色**：
- ✅ 代理层：转发请求到 MinerU Native API
- ✅ 临时文件存储：`/tmp/mineru_mcp_upload/{uuid}.pdf`
- ❌ **无持久化**：不存储任务状态
- ❌ **重启丢失**：容器重启后，活跃任务信息丢失

**文件流转路径**：
```
客户端上传 → MCP Server /api/parse
    ↓ 保存到 /tmp/mineru_mcp_upload/{uuid}.pdf
    ↓ POST /mineru_api/file_parse (或 /tasks)
MinerU Native API
    ↓ 处理文件
    ↓ 输出到 MinerU 指定目录（未知）
    ↓ 返回结果
MCP Server
    ↓ 返回给客户端
    ↓ 清理临时文件（可选）
```

---

## 2. 方案与现有架构的冲突

### 2.1 双重任务队列问题

**方案设计**：
```
MCP Server SQLite 任务队列
    ↓
MinerU Native API 任务队列
    ↓
实际处理
```

**问题**：
1. **双重存储**：MCP 存储任务 + MinerU 存储任务
2. **双重状态**：MCP 状态 ≠ MinerU 状态（需同步）
3. **双重 ID**：MCP task_id ≠ MinerU task_id（需映射）

**示例冲突**：
```python
# MCP Server 层
task_id_mcp = "uuid-1234"
status_mcp = "pending"
file_path = "output/2026/05/10/uuid-1234/input.pdf"

# MinerU Native API 层
task_id_mineru = "mineru-task-5678"  # 不同 ID
status_mineru = "processing"         # 不同状态
file_path = ??                       # MinerU 内部管理
```

### 2.2 文件路径冲突

**方案期望**：
- 上传文件存到：`output/2026/05/10/{uuid}/input.pdf`（持久化）
- MCP Server 管理：任务目录、文件路径

**当前行为**：
- 上传文件存到：`/tmp/mineru_mcp_upload/{uuid}.pdf`（临时）
- MinerU 管理：文件处理路径（未知）

**冲突**：
- MinerU Native API 可能有自己的文件存储逻辑
- 需要确认 MinerU 是否接受外部文件路径

### 2.3 并发控制冲突

**方案配置**：
```bash
MINERU_MAX_CONCURRENT=3  # MCP Server 并发上限
```

**MinerU 配置**：
```bash
MINERU_MAX_CONCURRENT=?  # MinerU Native API 并发上限（未知）
```

**问题**：
- 双重并发限制，可能导致实际并发数不匹配
- 需要确认 MinerU 的并发控制机制

---

## 3. 方案定位问题

### 3.1 三种可能定位

**定位 A：增强 MCP Server 层**
- 在 MCP Server 添加本地任务队列
- MCP Server 管理任务状态、文件路径
- 调用 MinerU Native API 处理（保留 MinerU 队列）
- **问题**：双重队列，架构复杂

**定位 B：绕过 MinerU Native API**
- MCP Server 直接调用 MinerU 核心解析函数
- 不通过 MinerU FastAPI
- MCP Server 完全管理任务队列
- **问题**：需要修改 MCP Server，失去 MinerU API 独立性

**定位 C：统一替换 MinerU 任务队列**
- 修改 MinerU Native API，使用新任务队列方案
- MCP Server 继续作为代理层
- **问题**：修改 MinerU 源码（不推荐）

### 3.2 推荐定位：**定位 A + 简化**

**简化方案**：
- MCP Server 添加**轻量级任务缓存层**（非完整队列）
- 目的：解决容器重启后任务丢失问题
- 不与 MinerU 队列竞争，只做状态同步

---

## 4. 关键问题待确认

### 4.1 MinerU Native API 内部实现

需要确认 MinerU FastAPI 内部：
1. **任务存储方式**：是否用 SQLite？表结构是什么？
2. **文件管理方式**：上传文件存哪里？输出文件存哪里？
3. **并发控制机制**：如何限制并发数？
4. **超时管理**：如何处理超时任务？
5. **目录结构**：是否已有日期分层？

**建议**：检查 MinerU 源码 `cli/fast_api.py` 或相关文件

### 4.2 All-in-One 模式文件共享

**关键问题**：
- MinerU Native API 和 MCP Server 在同一进程
- 文件路径是否共享？
- MinerU 能否访问 MCP Server 的 `output/` 目录？

**当前代码线索**：
```python
# app.py:98-100
from mineru.cli.fast_api import create_app as create_mineru_app
mineru_app = create_mineru_app()
routes.append(Mount("/mineru_api", app=mineru_app))
```

**推测**：MinerU FastAPI 挂载在同一应用，文件路径可能共享

---

## 5. 建议方案调整

### 5.1 简化任务队列设计

**原方案问题**：
- 方案假设需要完全新建任务队列
- 未考虑 MinerU Native API 已有功能

**建议调整**：
1. **先调研 MinerU**：确认 MinerU 已有任务队列实现
2. **定位方案**：明确是增强 MCP 还是替换 MinerU
3. **避免重复**：不重复实现 MinerU 已有功能

### 5.2 轻量级状态同步方案

**如果 MinerU 已有完整队列**，建议：

```
MCP Server 轻量级缓存层
├─ task_id 映射表：mcp_task_id → mineru_task_id
├─ 状态同步：定期轮询 MinerU 状态
├─ 启动恢复：重启时同步 MinerU 活跃任务
└─ 文件路径映射：mcp_path → mineru_path
```

**目的**：
- 解决 MCP Server 重启后任务丢失问题
- 不与 MinerU 队列竞争
- 保持架构清晰

### 5.3 深度整合方案（可选）

**如果希望统一管理**，建议：

```
绕过 MinerU Native API
├─ MCP Server 直接调用 MinerU 核心解析函数
├─ MCP Server 完全管理任务队列
├─ 统一文件路径：output/2026/05/10/{uuid}/
└─ 统一并发控制：MINERU_MAX_CONCURRENT
```

**优势**：
- 单一队列，架构简单
- 统一管理，控制清晰

**劣势**：
- 需要修改 MCP Server 代码
- 失去 MinerU API 独立性

---

## 6. 下一步行动建议

### 6.1 紧急：调研 MinerU 源码

**目标**：确认 MinerU Native API 已有功能

**方法**：
1. Clone MinerU 官方仓库
2. 检查 `cli/fast_api.py` 任务队列实现
3. 检查任务存储方式（SQLite？）
4. 检查文件管理方式
5. 检查并发控制机制

**预期产出**：
- MinerU 任务队列实现文档
- 与方案的契合度分析

### 6.2 方案定位决策

**需要用户决策**：
1. 是否保留 MinerU Native API？
2. 是否在 MCP Server 添加独立队列？
3. 是否绕过 MinerU API，直接调用核心函数？

**建议**：
- All-in-One 模式下，可考虑深度整合（定位 B）
- 分离部署模式下，保留 MinerU API（定位 A 简化）

### 6.3 方案文档修订

**修订任务队列方案**：
1. 补充 MinerU 已有功能分析
2. 明确方案定位（A/B/C）
3. 调整数据库设计（避免重复）
4. 调整目录结构（与 MinerU 契合）

---

## 7. 总结

**核心问题**：
- 方案未考虑 MinerU Native API 已有任务队列
- 可能导致双重队列、双重存储、架构复杂

**建议**：
1. 先调研 MinerU 源码，确认已有功能
2. 明确方案定位，避免重复实现
3. 根据定位调整方案设计

**风险**：
- 未调研就实施，可能导致架构混乱
- 双重队列增加维护成本

**✌Bazinga！**