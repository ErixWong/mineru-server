# 代码审计报告 - Task Queue System & Auth Module

**审计日期**: 2026-05-10  
**审计范围**: 未提交代码变更 + 新增文件  
**版本**: v0.2.0

---

## 1. 变更概览

### 修改文件 (7)
| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `.env.example` | 增强 | 添加任务队列配置说明 |
| `Dockerfile` | 增强 | 添加环境变量默认值 |
| `mcp-server/README.md` | 更新 | 版本更新到 v0.2.0 |
| `mcp-server/src/mineru_mcp/app.py` | 重构 | 添加 AuthMiddleware、双模式支持 |
| `mcp-server/src/mineru_mcp/cli.py` | 修复 | 更新导入路径 |
| `mcp-server/src/mineru_mcp/config.py` | 增强 | 添加任务队列配置项 |
| `mcp-server/src/mineru_mcp/errors.py` | 修复 | 修复运算符优先级 |
| `mcp-server/src/mineru_mcp/validation.py` | 增强 | 添加 validate_upload_file |

### 新增文件 (10+)
| 文件 | 说明 |
|------|------|
| `auth.py` | Bearer Token 认证模块 |
| `api_task_queue.py` | 任务队列模式 REST API |
| `server_task_queue.py` | 任务队列模式 MCP Server |
| `task_queue/__init__.py` | 模块入口 |
| `task_queue/database.py` | SQLite 数据库管理 |
| `task_queue/file_manager.py` | 文件管理 |
| `task_queue/processor.py` | 任务处理器 |
| `task_queue/scheduler.py` | 任务调度器 |
| `tests/test_*.py` | 测试文件 (3个) |

---

## 2. 严重问题 (Critical)

### 2.1 SQL 注入风险 - HIGH
**文件**: `task_queue/database.py:232-244`  
**位置**: `api_task_queue.py:80`

```python
# database.py - 问题代码
def count(self, sql: str, params: tuple = ()) -> int:
    """Count records."""
    with self._conn() as conn:
        result = conn.execute(sql, params).fetchone()
        return result[0] if result else 0
```

**风险**: `count()` 方法接受任意 SQL 字符串，虽然当前 `api_task_queue.py:80` 使用硬编码 SQL，但该方法设计允许任意 SQL 注入。如果未来传入用户可控的 SQL 字符串，将导致严重安全问题。

**建议**: 添加 SQL 白名单验证或限制只能使用预定义查询。

---

## 3. 重要问题 (High)

### 3.1 竞态条件 - 任务重复处理 - HIGH
**文件**: `task_queue/scheduler.py:99-134`

```python
async def _fetch_pending_tasks(self) -> None:
    active_count = self.processor.get_active_count()
    
    if active_count >= self.max_concurrent:
        return
        
    available_slots = self.max_concurrent - active_count
    
    tasks = self.db.fetch_all(
        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (available_slots,)
    )
    
    for task_data in tasks:
        task_id = task_data['task_id']
        
        updated = self.db.execute("""
            UPDATE tasks 
            SET status = 'processing', started_at = ?
            WHERE status = 'pending' AND task_id = ?
        """, (now, task_id))
        
        if updated > 0:
            task_data_updated = self.db.get_task(task_id)
            asyncio.create_task(self.processor.process_task(task_id, task_data_updated))
```

**问题**: 
1. 多个调度器实例可能同时读取到相同的 pending 任务
2. 虽然使用了 CAS (Compare-And-Swap) 更新，但 `fetch_all()` 和 `update()` 不是原子操作
3. 没有数据库事务保护，在高并发下可能导致任务被重复处理

**建议**: 
- 使用数据库事务包裹 fetch + update
- 添加唯一约束防止重复提交
- 考虑使用 `SELECT ... FOR UPDATE` (SQLite 需启用 WAL 模式)

---

## 4. 安全问题 (Security)

### 4.1 文件上传大小限制缺失 - MEDIUM
**文件**: `api_task_queue.py:150`

```python
content = await file.read()
safe_filename = validate_upload_file(file.filename, content)
```

**问题**: 虽然 `validate_upload_file()` 有 `max_size` 参数，但 FastAPI 没有配置请求体大小限制。大文件会在内存中完全读取，可能导致 DoS 攻击。

**建议**: 在 Starlette 应用中设置最大请求大小：
```python
# 在 create_unified_app 中添加
app = Starlette(...)
app.router.max_upload_size = 100 * 1024 * 1024  # 100MB
```

---

### 4.2 Base64 解码无大小限制 - MEDIUM
**文件**: `server_task_queue.py:115`, `server_task_queue.py:259`

```python
file_bytes = base64.b64decode(file_base64)
```

**问题**: Base64 解码后没有大小限制检查，恶意客户端可以发送巨大的 base64 字符串导致内存耗尽。

**建议**: 在解码后、使用前检查 `len(file_bytes)` 是否超过限制。

---

### 4.3 认证端点覆盖 - LOW
**文件**: `app.py:69`

```python
# Bypass auth for health endpoints (root and /health)
if path in ("/", "/health", "/api/health"):
```

**问题**: `/docs` 和 `/redoc` (FastAPI Swagger UI) 未排除认证，虽然设计上不需要，但应该明确文档说明。

**建议**: 添加注释说明哪些端点不需要认证及其原因。

---

## 5. 代码质量 (Code Quality)

### 5.1 代码重复 - HIGH
**文件**: `api_task_queue.py` vs `server_task_queue.py`

**问题**: 以下逻辑在两个文件中几乎完全重复：
1. 任务创建逻辑 (`api_task_queue.py:163-177`, `server_task_queue.py:129-142`)
2. 任务状态轮询逻辑 (`api_task_queue.py:181-214`, `server_task_queue.py:149-194`)
3. 图片获取逻辑 (`api_task_queue.py:400-470`, `server_task_queue.py:383-456`)

**建议**: 提取为共享函数或工具类，避免维护困难。

---

### 5.2 错误处理不一致 - LOW
**文件**: `api_task_queue.py:212`

```python
if task['status'] == 'failed':
    raise HTTPException(500, task['error'] or "Unknown error")
```

**问题**: 任务失败返回 HTTP 500，但根据失败原因可能应该返回不同的状态码（如 422 Unprocessable Entity）。

**建议**: 根据错误类型返回不同状态码，或添加错误码字段。

---

### 5.3 导入问题 - LOW
**文件**: `processor.py:13-25`

```python
try:
    from mineru.cli.common import aio_do_parse, read_fn
    MINERU_AVAILABLE = True
except ImportError as e:
    MINERU_AVAILABLE = False
    async def aio_do_parse(*args, **kwargs):
        raise NotImplementedError("MinerU not installed")
```

**问题**: 模块级 mock 函数会覆盖同名导入，虽然可行但不够优雅。

**建议**: 使用条件导入或 `sys.modules` 动态赋值。

---

### 5.4 errors.py 运算符优先级修复 - 已修复 ✅
**文件**: `errors.py:108`

```python
# 修复前 (原代码有 bug)
if isinstance(value, str) and "/" in value or "\\" in value:

# 修复后
if isinstance(value, str) and ("/" in value or "\\" in value):
```

**状态**: 已修复，运算符优先级问题已解决。

---

## 6. 性能问题 (Performance)

### 6.1 轮询效率 - MEDIUM
**文件**: `scheduler.py:84-97`

```python
while self._running:
    await asyncio.sleep(self.poll_interval)  # 固定 1 秒
    await self._fetch_pending_tasks()
    if self._running and self.timeout_check_enabled:
        await self._check_timeout_tasks()
```

**问题**: 
1. 每 1 秒轮询所有 pending 任务，即使没有新任务
2. `_check_timeout_tasks()` 每次查询所有 processing 任务，O(n) 复杂度

**建议**: 
- 使用数据库 NOTIFY/LISTEN 或 Redis Pub/Sub 替代轮询
- 为超时任务添加单独索引

---

### 6.2 数据库连接 - 每次操作新建 - LOW
**文件**: `database.py:86-101`

```python
@contextmanager
def _conn(self):
    conn = sqlite3.connect(self.db_path, timeout=30.0)
    # ...
```

**问题**: 每次数据库操作都创建新连接，虽然 SQLite 支持并发，但频繁创建/关闭连接有开销。

**建议**: 考虑使用连接池或长连接（需注意线程安全）。

---

## 7. 设计问题 (Design)

### 7.1 双模式架构复杂度 - MEDIUM
**文件**: `app.py:96-133`

```python
def create_api_app(config=None):
    if config.task_queue_enabled:
        from mineru_mcp.api_task_queue import create_api_app as create_api_task_queue
        return create_api_task_queue()
    else:
        from mineru_mcp.api import create_api_app as create_api_http
        return create_api_http()
```

**问题**: 运行时动态切换模式增加了复杂性，可能导致：
1. 配置错误时难以调试
2. 两种 API 行为不一致

**建议**: 考虑明确分离两个可独立部署的服务，或使用特性标志(Feature Flag)而非运行时切换。

---

### 7.2 同步解析端点设计 - MEDIUM
**文件**: `api_task_queue.py:110-227`

```python
@app.post("/parse")
async def parse_pdf_sync(...):
    # ... 创建任务
    while asyncio.get_running_loop().time() - start_wait < timeout:
        task = db.get_task(task_id)
        if task['status'] == 'completed':
            return {"markdown": markdown_content}
        await asyncio.sleep(1)
```

**问题**: 
1. `/parse` 端点本质上是一个同步端点，但使用异步轮询实现
2. HTTP 连接会一直保持到任务完成，可能触发代理/网关超时
3. 与 `/tasks` 异步端点功能重叠

**建议**: 移除 `/parse` 端点，只保留异步 `/tasks` + 状态查询模式。

---

### 7.3 时间处理不一致 - LOW
**文件**: `database.py:164`, `scheduler.py:141`

```python
# database.py
now = datetime.now().isoformat()

# scheduler.py
now = datetime.now()
```

**问题**: 混用带时区和不带时区的时间格式，可能导致比较问题。

**建议**: 统一使用 `datetime.now(timezone.utc)` 或 `datetime.utcnow()`。

---

## 8. 测试覆盖 (Testing)

### 8.1 已有测试 ✅
- `tests/test_task_queue_basic.py` - 基础功能测试
- `tests/test_auth_integration.py` - 认证集成测试
- `tests/test_api_integration.py` - API 集成测试

### 8.2 缺失测试 - MEDIUM
以下功能缺少测试覆盖：
- `TaskDatabase` 并发写入
- `TaskScheduler` 超时检测
- `AuthMiddleware` 完整流程
- `FileManager` 边界条件
- `TaskProcessor` MinerU 不可用时的行为
- 竞态条件场景测试

---

## 9. 文档 (Documentation)

### 9.1 文档更新良好 ✅
- README.md 已更新到 v0.2.0
- 新增任务队列配置说明
- API 端点文档完整
- `.env.example` 添加了详细注释

### 9.2 缺少的文档
- 任务队列架构图
- 故障转移/恢复流程
- 性能基准测试数据

---

## 10. Dockerfile 检查

### 10.1 环境变量分组清晰 ✅
**文件**: `Dockerfile`

```dockerfile
# MCP Server Configuration
ENV MCP_SERVER_MODE=http ...

# MinerU Configuration
ENV MINERU_OUTPUT_ROOT=/app/output ...

# Task Queue Configuration (NEW)
ENV MINERU_TASK_QUEUE_ENABLED=true ...

# Authentication (Optional)
# ENV MCP_HTTP_AUTH_TOKEN=your-secure-token-here
```

**评价**: 环境变量分组清晰，注释详细。

### 10.2 健康检查配置 ✅
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
```

**评价**: 健康检查参数合理，start-period 给足了初始化时间。

---

## 11. 总结

### 问题统计

| 级别 | 数量 | 说明 |
|------|------|------|
| Critical | 0 | - |
| High | 2 | SQL 注入风险、竞态条件 |
| Medium | 5 | 安全、性能、设计问题 |
| Low | 5 | 代码质量、文档完善 |

### 已修复问题

| 问题 | 文件 | 状态 |
|------|------|------|
| datetime.timedelta 缺失 | database.py | 已修复 ✅ |
| read_fn 同步阻塞 | processor.py | 已修复 (使用 asyncio.to_thread) ✅ |
| process_task await 阻塞 | processor.py | 已修复 (使用回调) ✅ |
| PRAGMA 位置 | database.py | 已修复 (在 _conn 中) ✅ |
| 运算符优先级 | errors.py | 已修复 ✅ |
| import re 位置 | validation.py | 已修复 (移到顶部) ✅ |

### 优先级修复建议

1. **立即修复 (v0.2.1)**:
   - [ ] SQL 注入防护 (添加方法使用限制)
   - [ ] 竞态条件 (添加事务保护)
   - [ ] 文件上传大小限制

2. **短期优化 (v0.3.0)**:
   - [ ] 代码重复提取
   - [ ] 同步端点移除
   - [ ] 时区统一
   - [ ] 补充测试覆盖

3. **长期规划**:
   - [ ] 考虑分布式任务队列 (Celery/RQ)
   - [ ] 添加监控指标 (Prometheus)
   - [ ] 数据库连接池优化

---

**审计结论**: 代码整体结构良好，任务队列系统设计合理，认证模块实现规范（使用了安全的 `secrets.compare_digest` 方法）。之前的 P0 问题（timedelta 缺失、read_fn 阻塞、process_task 阻塞）均已修复。主要待改进点是竞态条件和代码重复问题。

✌Bazinga！
