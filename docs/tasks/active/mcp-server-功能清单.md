# MCP Server 功能清单

**架构**：
```
/mcp          → MCP Tools（MCP 协议）
/api          → MCP Server REST API（增强功能）
/mineru_api   → 代理 MinerU 原生 API（基础解析）
```

---

## 1. MCP Tools（/mcp）

**协议**: MCP (Model Context Protocol)
**适用**: Claude Desktop, Cline, 其他 MCP Client

### Tools 列表（6 个）

| Tool | 功能 | 参数 |
|------|------|------|
| **parse_pdf** | 同步解析 PDF，返回 Markdown | file_path, backend, lang, formula_enable, table_enable, start_page_id, end_page_id |
| **submit_task** | 异步提交解析任务，返回 task_id | file_path, backend, lang, formula_enable, table_enable, start_page_id, end_page_id |
| **get_task** | 查询任务状态和结果 | task_id, return_md |
| **get_images** | 获取解析的图片（Base64） | task_id |
| **list_backends** | 列出所有解析后端 | 无 |
| **health_check** | 检查 MinerU API 健康状态 | 无 |

---

## 2. REST API（/api）

**协议**: HTTP REST
**适用**: 远程 HTTP 调用，浏览器，其他 HTTP Client

### Endpoints 列表（6 个）

| Endpoint | 方法 | 功能 | 说明 |
|----------|------|------|------|
| `/health` | GET | 健康检查 | 检查 MinerU API 是否可用 |
| `/backends` | GET | 列出后端 | 列出所有支持的解析后端 |
| `/parse` | POST | 同步解析 | 解析 PDF，返回 Markdown |
| `/tasks` | POST | 异步提交 | 提交解析任务，返回 task_id |
| `/tasks/{task_id}` | GET | 查询任务 | 查询任务状态和 Markdown 结果 |
| `/tasks/{task_id}/images` | GET | 获取图片 | 获取任务的图片（Base64） |

---

## 3. MinerU 原生 API（需添加代理 /mineru_api）

**来源**: MinerU FastAPI（src/mineru/cli/fast_api.py）
**功能**: 基础 PDF 解析功能

### 原生 Endpoints（需代理）

| Endpoint | 方法 | 功能 | 说明 |
|----------|------|------|------|
| `/file_parse` | POST | 同步解析 PDF | MinerU 基础解析 API |
| `/tasks` | POST | 异步提交任务 | MinerU 异步任务 API |
| `/tasks/{task_id}` | GET | 查询任务状态 | MinerU 任务状态查询 |
| `/tasks/{task_id}/result` | GET | 获取任务结果 | MinerU 结果获取（含 ZIP） |
| `/health` | GET | 健康检查 | MinerU 健康检查 |

---

## 4. 功能对比

### 4.1 MCP Tools vs REST API

**对比**：
| 功能 | MCP Tools | REST API | 说明 |
|------|-----------|----------|------|
| 同步解析 | parse_pdf | /parse | ✅ 两者都有 |
| 异步提交 | submit_task | /tasks | ✅ 两者都有 |
| 查询任务 | get_task | /tasks/{id} | ✅ 两者都有 |
| 获取图片 | get_images | /tasks/{id}/images | ✅ 两者都有 |
| 健康检查 | health_check | /health | ✅ 两者都有 |
| 列出后端 | list_backends | /backends | ✅ 两者都有 |

**结论**: MCP Tools 和 REST API 功能一致，只是协议不同

---

### 4.2 MCP Server API vs MinerU 原生 API

**对比**：
| 功能 | MCP Server API | MinerU 原生 API | 差异 |
|------|---------------|----------------|------|
| 同步解析 | /parse | /file_parse | ✅ 相同 |
| 异步提交 | /tasks | /tasks | ✅ 相同 |
| 查询状态 | /tasks/{id} | /tasks/{id} | ⚠️ MCP 增强版（聚合 Markdown） |
| 获取结果 | /tasks/{id}/images | /tasks/{id}/result | ⚠️ MCP 提取图片，MinerU 返回 ZIP |
| 健康检查 | /health | /health | ✅ 相同 |
| 认证 | Bearer Token | 无 | ⚠️ MCP 增加认证 |
| 验证 | 文件路径、后端验证 | 无 | ⚠️ MCP 增加验证 |
| 错误处理 | 结构化错误码 | HTTP 状态码 | ⚠️ MCP 增强错误处理 |

---

## 5. 缺失功能（需要添加）

### 5.1 任务管理功能（缺失 ⚠️）

**当前问题**：
- ❌ 无任务数据库存储
- ❌ 无任务历史查询
- ❌ 无任务列表查询（/tasks?status=completed）
- ❌ 无任务删除功能

**需要添加**：
| Endpoint | 方法 | 功能 | 说明 |
|----------|------|------|------|
| `/tasks` | GET | 列出所有任务 | 查询任务列表（支持过滤） |
| `/tasks/{task_id}` | DELETE | 删除任务 | 删除任务和结果文件 |
| `/tasks/stats` | GET | 任务统计 | 统计任务状态（pending/processing/completed/failed） |

---

### 5.2 文件管理功能（缺失 ⚠️）

**当前问题**：
- ❌ 无文件上传历史
- ❌ 无文件列表查询
- ❌ 无文件下载功能（非任务结果）

**需要添加**：
| Endpoint | 方法 | 功能 | 说明 |
|----------|------|------|------|
| `/files` | GET | 列出上传文件 | 查询上传的文件列表 |
| `/files/{file_id}` | GET | 下载文件 | 下载原始上传文件 |
| `/files/{file_id}` | DELETE | 删除文件 | 删除上传的文件 |

---

### 5.3 结果管理功能（部分缺失 ⚠️）

**当前有**：
- ✅ `/tasks/{id}/images` - 获取图片

**缺少**：
| Endpoint | 方法 | 功能 | 说明 |
|----------|------|------|------|
| `/tasks/{task_id}/download` | GET | 下载 ZIP | 下载完整结果 ZIP |
| `/tasks/{task_id}/markdown` | GET | 下载 Markdown | 仅下载 Markdown 文件 |
| `/tasks/{task_id}/middle_json` | GET | 下载 middle JSON | 下载中间 JSON 结果 |

---

## 6. MinerU 原生 API 代理（需添加）

**建议路由**：
```
/mineru_api → 代理到 MinerU FastAPI（localhost:8000 或 内嵌 MinerU）
```

**实现方式**：
```python
# app.py
if enable_mineru_proxy:
    from starlette.routing import Mount
    routes.append(Mount("/mineru_api", app=mineru_app))
```

---

## 7. 完整架构（建议）

```
/mcp                    → MCP Tools（6 个）
    - parse_pdf
    - submit_task
    - get_task
    - get_images
    - list_backends
    - health_check

/api                    → MCP Server REST API（6 个基础 + 6 个增强）
    基础功能（已有）：
    - GET  /health
    - GET  /backends
    - POST /parse
    - POST /tasks
    - GET  /tasks/{task_id}
    - GET  /tasks/{task_id}/images
    
    增强功能（需添加）：
    - GET    /tasks                # 任务列表
    - DELETE /tasks/{task_id}      # 删除任务
    - GET    /tasks/stats          # 任务统计
    - GET    /files                # 文件列表
    - GET    /files/{file_id}      # 下载文件
    - DELETE /files/{file_id}      # 删除文件

/mineru_api             → MinerU 原生 API（代理）
    - POST /file_parse              # MinerU 原生同步解析
    - POST /tasks                   # MinerU 原生异步提交
    - GET  /tasks/{task_id}         # MinerU 原生状态查询
    - GET  /tasks/{task_id}/result  # MinerU 原生结果（ZIP）
    - GET  /health                  # MinerU 原生健康检查
```

---

## 8. 下一步行动

### 8.1 立即可做（Phase 2）

1. ✅ 添加 `/mineru_api` 代理路由（已有 enable_mineru）
2. ✅ 检查当前功能是否完整

### 8.2 后续增强（Phase 3）

1. 添加任务列表查询（GET /tasks）
2. 添加任务删除（DELETE /tasks/{id}）
3. 添加文件管理（GET /files, DELETE /files/{id}）
4. 添加结果下载（GET /tasks/{id}/download, /markdown, /middle_json）

---

✌Bazinga！