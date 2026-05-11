# 任务队列方案架构审视报告（最终版）

**日期**: 2026-05-10
**审视角度**: 系统架构设计师
**状态**: Critical Issues Found

---

## 1. 输出路径结构矛盾 ⚠️

### 1.1 方案描述

```
output/2026/05/10/{uuid}/
├── input.pdf          # 上传的原始文件
└── output/            # MinerU 输出目录 ❌ 错误
    ├── *.md
    └── *.json
```

### 1.2 MinerU 实际输出

根据 MinerU 调研（`docs/mineru/mineru-task-queue-analysis.md`）：

```
{output_dir}/{pdf_name}/{parse_method}/
├── {pdf_name}.md
├── {pdf_name}_middle.json
├── {pdf_name}_model.json
└── images/
    ├── image_001.jpg
    └── image_002.png
```

**实际示例**：
- `output_dir = "./output/2026/05/10/{uuid}/"`
- `pdf_name = "document"`（从 input.pdf 提取）
- `parse_method = "vlm"`（backend 类型）
- 最终路径：`output/2026/05/10/{uuid}/document/vlm/document.md`

### 1.3 方案修正

**修正后的目录结构**：

```
output/2026/05/10/{uuid}/
├── input.pdf                 # 上传的原始文件
└── {pdf_name}/               # MinerU 输出目录（pdf_name = input.pdf 的文件名）
    ├── vlm/                  # backend 类型
    │   ├── {pdf_name}.md
    │   ├── {pdf_name}_middle.json
    │   ├── {pdf_name}_model.json
    │   ├── {pdf_name}_content_list.json
    │   └── images/
    │       ├── image_001.jpg
    │       └── image_002.png
    └── hybrid_vlm/           # hybrid backend
        └── ...
```

**数据库注释修正**：
```sql
-- 约定:
-- 输入文件路径: {task_dir}{input_filename}
-- 输出目录路径: {task_dir}{pdf_name}/{backend}/  (MinerU 输出结构)
-- pdf_name: 从 input_filename 提取（去掉扩展名）
-- backend: vlm, pipeline, hybrid_vlm 等
```

---

## 2. Worker 进程设计错误 ⚠️

### 2.1 方案描述

```
Worker 进程 (循环)
    ↓
查询 tasks 表
```

### 2.2 问题

- MCP Server 是**单进程架构**（All-in-One 模式）
- 不应该启动独立 Worker 进程
- 应该在**同一进程内启动 asyncio 协程**

### 2.3 修正

**任务调度器（协程模式）**：

```python
class TaskScheduler:
    def __init__(self, processor: TaskProcessor):
        self.processor = processor
        self._scheduler_task: asyncio.Task = None
        
    async def start(self):
        """启动任务调度协程（在 MCP Server 进程内）"""
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
    async def stop(self):
        """停止任务调度协程"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            
    async def _scheduler_loop(self):
        """任务调度循环（协程）"""
        while True:
            # 查询待处理任务
            pending_tasks = db.fetch_all(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC"
            )
            
            for task in pending_tasks:
                # 启动处理协程
                asyncio.create_task(
                    self.processor.process_task(task['task_id'], task)
                )
            
            await asyncio.sleep(1)
```

**启动方式（在 app.py lifespan 中）**：

```python
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    scheduler = TaskScheduler(processor)
    await scheduler.start()  # 启动调度协程
    yield
    await scheduler.stop()   # 停止调度协程
```

---

## 3. 并发控制逻辑问题 ⚠️

### 3.1 方案代码

```python
async def worker_loop(self):
    while True:
        pending_tasks = self.db.fetch_all(...)
        
        for task in pending_tasks:
            # ❌ 无限创建任务，然后被 Semaphore 阻塞
            task_coro = asyncio.create_task(
                self.process_task(task['task_id'], task)
            )
            self.active_tasks[task['task_id']] = task_coro
            
        await asyncio.sleep(1)
```

### 3.2 问题

- 直接创建无限任务，然后依赖 Semaphore 阻塞
- 导致大量任务对象堆积在内存中
- 不符合"最多 N 个并发"的设计意图

### 3.3 修正方案 A：批量领取

```python
async def _scheduler_loop(self):
    while True:
        # 检查当前活跃任务数
        active_count = len(self.processor.active_tasks)
        available_slots = max(0, self.config.max_concurrent - active_count)
        
        if available_slots == 0:
            await asyncio.sleep(1)
            continue
        
        # 批量领取任务（不超过可用槽位）
        pending_tasks = db.fetch_all("""
            SELECT * FROM tasks 
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT ?
        """, (available_slots,))
        
        for task in pending_tasks:
            asyncio.create_task(self.processor.process_task(task['task_id'], task))
        
        await asyncio.sleep(1)
```

### 3.4 修正方案 B：数据库乐观锁（推荐）

```python
async def _scheduler_loop(self):
    while True:
        # 乐观锁领取任务
        task_id = db.execute("""
            UPDATE tasks 
            SET status = 'processing', started_at = NOW(), timeout_at = NOW() + timeout
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT 1
            RETURNING task_id
        """)
        
        if task_id:
            # 只有领取成功才创建任务
            asyncio.create_task(self.processor.process_task(task_id))
        else:
            await asyncio.sleep(1)
```

---

## 4. 与现有 MCP Server 架构整合问题 ⚠️

### 4.1 现有 MCP Server 功能

根据代码分析（`mcp-server/src/mineru_mcp/`）：

| 模块 | 功能 | 状态 |
|------|------|------|
| `mineru_client.py` | MinerU HTTP 客户端 | 完整实现 |
| `server.py` | MCP 工具（parse_pdf, submit_task, get_task） | 完整实现 |
| `api.py` | REST API（/api/parse, /api/tasks） | 完整实现 |
| `concurrency.py` | 并发控制（RateLimiter, ConcurrentTaskLimiter） | 完整实现 |
| `entrypoint.py` | All-in-One 容器入口 | 完整实现 |

### 4.2 方案与现有架构冲突

**方案定位 B（直接调用 MinerU 核心）会导致**：

| 现有功能 | 方案影响 | 处理方式 |
|---------|---------|---------|
| `mineru_client.py` | 完全废弃 ❌ | 替换为 `TaskProcessor` |
| `server.py` MCP 工具 | 需重构 ❌ | 重写 MCP 工具 |
| `api.py` REST API | 需重构 ❌ | 重写 API 端点 |
| `concurrency.py` | 可复用 ✅ | Semaphore 模式可复用 |
| `entrypoint.py` | 需修改 ⚠️ | 增加 TaskScheduler 启动 |

### 4.3 整合策略建议

**策略 A：重构现有模块**

```
mcp-server/src/mineru_mcp/
├── mineru_client.py      → 删除（不再需要 HTTP 客户端）
├── task_processor.py     → 新增（直接调用 aio_do_parse）
├── task_scheduler.py     → 新增（任务调度协程）
├── database.py           → 新增（SQLite 操作）
├── server.py             → 重构（修改 MCP 工具）
├── api.py                → 重构（修改 REST API）
├── concurrency.py        → 复用（Semaphore 模式）
└── app.py                → 修改（启动 TaskScheduler）
```

**策略 B：渐进式迁移**

- Phase 1: 新增 `task_processor.py`，保留 `mineru_client.py`（双模式）
- Phase 2: 新增 `task_scheduler.py`，测试直接调用模式
- Phase 3: 重构 `server.py` 和 `api.py`
- Phase 4: 删除 `mineru_client.py`

---

## 5. 文件上传临时目录 vs 持久化目录 ⚠️

### 5.1 现有实现

```python
# api.py:30-48
def _save_upload_file(file: UploadFile) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "mineru_mcp_upload"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    unique_name = f"{uuid.uuid4()}{Path(file.filename).suffix}"
    temp_path = temp_dir / unique_name
    
    content = file.file.read()
    temp_path.write_bytes(content)
    
    return temp_path  # 返回临时文件路径
```

### 5.2 方案期望

- 文件保存到持久化目录：`output/2026/05/10/{uuid}/input.pdf`
- 临时文件应该在处理完成后清理

### 5.3 修正

**直接保存到持久化目录**：

```python
def _save_upload_file_persistent(file: UploadFile) -> tuple[Path, str]:
    """保存到持久化目录（日期分层）"""
    task_id = str(uuid.uuid4())
    today = datetime.now()
    task_dir = Path(f"output/{today.year}/{today.month:02d}/{today.day:02d}/{task_id}")
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    input_filename = f"input{Path(file.filename).suffix}"
    input_path = task_dir / input_filename
    
    content = file.file.read()
    input_path.write_bytes(content)
    
    return input_path, task_id  # 返回持久化路径和 task_id
```

---

## 6. 超时机制设计冲突 ⚠️

### 6.1 方案中的两种超时机制

**机制 A**：`asyncio.wait_for`（主动超时）
```python
result = await asyncio.wait_for(process_task, timeout=timeout)
```

**机制 B**：后台监控协程（被动监控）
```python
async def _timeout_monitor(self, task_id: str, timeout: int):
    await asyncio.sleep(timeout)
    task.cancel()
```

### 6.2 问题

- 两种机制可能冲突
- `asyncio.wait_for` 已经足够，不需要额外监控协程
- 监控协程方案复杂，且有并发问题

### 6.3 修正

**简化为单一机制**：

```python
async def process_task_with_timeout(self, task_id: str, task_data: dict):
    """带超时的处理（单一机制）"""
    timeout = task_data.get('timeout_seconds', 3600)
    
    try:
        # 使用 asyncio.wait_for 统一管理超时
        await asyncio.wait_for(
            self._process_internal(task_id, task_data),
            timeout=timeout
        )
        db.update_status(task_id, "completed")
    except asyncio.TimeoutError:
        db.update_status(task_id, "failed", error="Timeout")
    except asyncio.CancelledError:
        db.update_status(task_id, "cancelled")
    except Exception as e:
        db.update_status(task_id, "failed", error=str(e))
```

**数据库定时清理超时任务（辅助机制）**：

```python
async def cleanup_timeout_tasks():
    """定期清理数据库中的超时记录（不负责实时取消）"""
    while True:
        await asyncio.sleep(60)
        
        # 查找超时但未清理的任务（可能因为进程崩溃）
        timeout_tasks = db.fetch_all("""
            SELECT task_id FROM tasks 
            WHERE status = 'processing' AND timeout_at < NOW()
        """)
        
        # 这些任务应该已经崩溃，标记为 failed
        for task_id in timeout_tasks:
            db.update_status(task_id, "failed", error="Process crashed")
```

---

## 7. MCP 工具重构细节 ⚠️

### 7.1 现有 MCP 工具

```python
# server.py
@mcp.tool()
async def parse_pdf(file_path: str, backend: str = None, ...):
    # 调用 MinerUClient
    
@mcp.tool()
async def submit_task(file_path: str, backend: str = None, ...):
    # 调用 MinerUClient
    
@mcp.tool()
async def get_task(task_id: str, ...):
    # 调用 MinerUClient
```

### 7.2 方案重构

```python
# server.py（重构后）
@mcp.tool()
async def mineru_parse_submit(file_path: str, backend: str = "vlm-auto-engine", ...):
    """提交解析任务到本地队列"""
    # 1. 保存文件到持久化目录
    task_id, task_dir = save_file_to_task_dir(file_path)
    
    # 2. 创建数据库记录
    db.create_task(task_id, task_dir, file_path, backend, ...)
    
    # 3. 返回 task_id（任务调度器会自动处理）
    return {"task_id": task_id, "status": "pending"}

@mcp.tool()
async def mineru_parse_status(task_id: str):
    """查询任务状态"""
    task = db.get_task(task_id)
    return {
        "task_id": task_id,
        "status": task["status"],
        "created_at": task["created_at"],
        "started_at": task["started_at"],
        "completed_at": task["completed_at"],
        "error": task["error_message"],
    }

@mcp.tool()
async def mineru_parse_result(task_id: str, return_md: bool = True):
    """获取解析结果"""
    task = db.get_task(task_id)
    if task["status"] != "completed":
        raise ValueError("Task not completed")
    
    # 从文件读取结果
    result_dir = Path(task["task_dir"]) / task["pdf_name"] / "vlm"
    md_path = result_dir / f"{task['pdf_name']}.md"
    
    if return_md:
        return {"markdown": md_path.read_text()}
    else:
        return {"result_dir": str(result_dir)}

@mcp.tool()
async def mineru_parse_cancel(task_id: str):
    """取消任务"""
    task = db.get_task(task_id)
    if task["status"] == "processing":
        # 找到对应的 asyncio.Task 并取消
        processor.cancel_task(task_id)
    db.update_status(task_id, "cancelled")
```

---

## 8. 优先级与实施计划修正

### 8.1 修正后的实施计划

**Phase 1：基础设施（P0）**

- [ ] SQLite 数据库初始化（database.py）
- [ ] 任务队列表结构创建
- [ ] 文件上传保存到持久化目录（修改 api.py）
- [ ] 基础 MCP 工具重构（submit, status）

**Phase 2：任务处理器（P0）**

- [ ] TaskProcessor 实现（直接调用 aio_do_parse）
- [ ] TaskScheduler 协程（任务调度）
- [ ] Semaphore 并发控制（复用 concurrency.py）
- [ ] 启动集成（修改 app.py lifespan）

**Phase 3：超时与恢复（P1）**

- [ ] asyncio.wait_for 超时机制
- [ ] 容器重启恢复逻辑
- [ ] 重试机制（可选）

**Phase 4：完整功能（P1）**

- [ ] MCP 工具完整重构（result, cancel, list）
- [ ] REST API 完整重构
- [ ] 监控指标 API

**Phase 5：清理与维护（P2）**

- [ ] 定期清理旧任务
- [ ] 错误日志记录
- [ ] 性能监控

---

## 9. 关键风险清单

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| MinerU 输出路径理解错误 | High | 已修正，更新方案 |
| Worker 进程设计错误 | High | 改为协程模式 |
| 并发控制逻辑问题 | High | 乐观锁领取方案 |
| 现有架构冲突 | Medium | 渐进式迁移策略 |
| 超时机制冲突 | Medium | 简化为单一机制 |
| 数据库并发限制 | Low | SQLite WAL 模式 |
| 磁盘空间不足 | Low | 定期清理 + 监控 |

---

## 10. 总结建议

### 10.1 方案可行性

**总体评估**：方案核心思路正确（直接调用 MinerU 核心），但细节设计存在多处错误。

**需要修正的点**：
1. ✅ MinerU 输出路径结构（已明确）
2. ✅ Worker 进程改为协程模式
3. ✅ 并发控制逻辑（乐观锁领取）
4. ⚠️ 与现有架构整合策略
5. ✅ 超时机制简化

### 10.2 下一步行动

1. **更新方案文档**：修正上述错误
2. **设计整合策略**：明确如何修改现有代码
3. **开始实施 Phase 1**：数据库 + 文件上传

**✌Bazinga！**