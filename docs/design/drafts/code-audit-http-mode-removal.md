# 代码审计报告 - HTTP 模式移除

**审计日期**: 2026-05-11  
**变更范围**: 移除 HTTP 模式，简化为 Task Queue 单一架构  
**变更统计**: 16 文件, +829 -1135 行

---

## 1. 变更概览

### 删除文件
| 文件 | 说明 |
|------|------|
| `mineru_client.py` | MinerU HTTP API 客户端（351行） |
| `entrypoint.py` | MinerU API 启动入口（58行） |

### 修改文件
| 文件 | 变更 |
|------|------|
| `app.py` | 移除 `enable_mineru_api` 参数，简化 `create_api_app`/`create_mcp_server` |
| `cli.py` | 移除 `--mineru-api-base`, `--enable-mineru-api` 参数 |
| `config.py` | 移除 `mineru_api_base`, `task_queue_enabled` 配置项 |
| `api.py` | 从 HTTP 模式改为直接使用 TaskDatabase |
| `server.py` | 从 HTTP 模式改为直接使用 TaskDatabase |
| `__init__.py` | 移除 MinerUClient 导出 |
| `.env.example` | 移除 `MINERU_API_BASE` |

---

## 2. 代码质量评估

### 2.1 架构简化 ✅ 优秀

**变更前**: 双模式切换
```python
if config.task_queue_enabled:
    from mineru_mcp.api_task_queue import ...
else:
    from mineru_mcp.api import ...  # HTTP 模式
```

**变更后**: 单一模式
```python
from mineru_mcp.api import create_api_app as create_api_impl
return create_api_impl()
```

**评价**: 移除条件分支，降低维护复杂度，代码路径更清晰。

### 2.2 配置简化 ✅ 良好

移除了不必要的配置项：
- `MINERU_API_BASE` - 不再需要 MinerU API 地址
- `MINERU_TASK_QUEUE_ENABLED` - 默认启用，无需配置

保留的配置项合理：
- `MINERU_MAX_CONCURRENT` - 并发控制
- `MINERU_TASK_TIMEOUT` - 超时设置
- `MINERU_DB_PATH` - 数据库路径

### 2.3 导入清理 ✅ 良好

`__init__.py` 移除：
- `MinerUClient`, `get_client`, `reset_client`
- `mineru_api_error`, `mineru_api_unavailable`

无残留引用。

---

## 3. 安全性评估

### 3.1 认证中间件 ✅ 良好

`app.py:51-93` AuthMiddleware 实现：
- 使用 `secrets.compare_digest` (通过 `check_auth_header`)
- 健康检查端点豁免认证
- OPTIONS 请求豁免（CORS preflight）

### 3.2 文件上传安全 ✅ 良好

`validation.py:341-408` `validate_upload_file`:
- 文件大小限制 (`MAX_FILE_SIZE`)
- 扩展名白名单验证
- 文件名脱敏（移除路径组件）
- 空文件检查

### 3.3 SQL 查询 ⚠️ 注意

`api.py:79-84` 使用硬编码 SQL：
```python
db.count("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
```

当前安全（硬编码），但 `database.py` 的 `count()` 方法设计允许任意 SQL。建议添加注释警告。

---

## 4. 潜在问题

### 4.1 Base64 解码无大小限制 - Medium

**位置**: `server.py:112`

```python
file_bytes = base64.b64decode(file_base64)
```

**问题**: 解码后未检查大小，恶意客户端可发送超大 base64 导致内存耗尽。

**建议**: 
```python
file_bytes = base64.b64decode(file_base64)
if len(file_bytes) > MAX_FILE_SIZE:
    raise ValidationError(ERROR_FILE_TOO_LARGE, ...)
```

### 4.2 Dockerfile CMD 参数残留 - Low

**位置**: `Dockerfile:80`

```dockerfile
CMD ["mineru-mcp", "--mode", "http", "--port", "8001", "--enable-mineru-api"]
```

`--enable-mineru-api` 参数已从 `cli.py` 移除，但 Dockerfile 未更新。

**建议**: 
```dockerfile
CMD ["mineru-mcp", "--mode", "http", "--port", "8001"]
```

### 4.3 循环导入风险 - Low

**位置**: 
- `api.py:30` → `from mineru_mcp.app import _start_time`
- `api.py:56` → `from mineru_mcp.app import _task_scheduler`
- `server.py:322` → `from mineru_mcp.app import _task_scheduler`

**问题**: 运行时动态导入可工作，但增加依赖复杂度。

**建议**: 考虑将 `_task_scheduler` 和 `_start_time` 移到独立模块。

---

## 5. 文件末尾格式

以下文件缺少换行符：
- `mcp-server/src/mineru_mcp/__init__.py:152` (无换行)
- `mcp-server/src/mineru_mcp/api.py:331` (无换行)

建议添加末尾换行符（POSIX 标准）。

---

## 6. 测试覆盖

变更后需要更新/新增测试：
- 移除 `MinerUClient` 相关测试
- 更新 `cli.py` 测试（移除参数）
- 更新配置测试（移除字段）
- 新增 Base64 大小限制测试

---

## 7. 总结

| 类别 | 评分 |
|------|------|
| 架构设计 | ⭐⭐⭐⭐⭐ 优秀 |
| 代码质量 | ⭐⭐⭐⭐ 良好 |
| 安全性 | ⭐⭐⭐⭐ 良好 |
| 文档完整性 | ⭐⭐⭐⭐ 良好 |

### 需立即修复
1. Dockerfile CMD 参数移除 `--enable-mineru-api`
2. `server.py` 添加 Base64 解码大小检查

### 可选优化
1. 文件末尾换行符
2. SQL 方法添加安全注释
3. 循环导入解耦

---

## 8. 审计结论

HTTP 模式移除成功，架构显著简化：
- 代码减少 306 行
- 条件分支移除
- 配置项减少

主要风险：Base64 解码无大小限制（继承自原代码，非新引入）。

建议修复 Dockerfile CMD 参数后可提交。

✌Bazinga！