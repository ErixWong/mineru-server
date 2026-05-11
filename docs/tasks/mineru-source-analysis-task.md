# MinerU 源码调研任务

## 任务状态：已完成 ✅

## 完成时间：2026-05-10

## 调研范围

位于 `D:\projects\github\mineru` 的 MinerU 源码

## 输出文档

1. **mineru-task-queue-analysis.md** - MinerU 任务队列实现完整分析
2. **mineru-database-schema.md** - 数据库表结构（实际无 SQLite）
3. **mineru-mcp-integration-analysis.md** - MCP Server 任务队列契合度分析

## 关键发现摘要

### 1. FastAPI 实现

- 主文件：`mineru/cli/fast_api.py`
- 端点：
  - `POST /tasks` - 异步提交任务（返回 202）
  - `POST /file_parse` - 同步解析等待结果（返回 200）
  - `GET /tasks/{id}` - 状态查询
  - `GET /tasks/{id}/result` - 结果获取
  - `GET /health` - 健康检查

### 2. 任务队列机制

- **无 SQLite**：全部内存存储
- 核心：`AsyncTaskManager` 类
- 存储：`dict[str, AsyncParseTask]` + `asyncio.Queue`
- 状态：pending → processing → completed/failed

### 3. 并发控制

- `asyncio.Semaphore` 限制并发
- 默认：3 个并发请求
- 环境变量：`MINERU_API_MAX_CONCURRENT_REQUESTS`
- Mac 环境：强制限制为 1

### 4. 文件存储

- 上传文件：`{output_root}/{task_id}/uploads/`
- 输出文件：`{output_root}/{task_id}/{file_name}/{backend}/`
- 无日期分层

### 5. 任务清理

- 默认保留：24 小时
- 清理间隔：5 分钟
- 环境变量可配置

### 6. 超时管理

- 客户端超时：有（1 小时等待）
- **服务端超时：无**（任务不会被主动取消）
- 这是重要缺陷

### 7. 核心解析函数

- `aio_do_parse()` - 异步版本，可直接调用
- `do_parse()` - 同步版本
- **非常适合 MCP Server 直接集成**

## MCP Server 集成建议

1. **直接调用** `aio_do_parse()`，不启动 FastAPI
2. **新增 SQLite** 持久化存储
3. **新增超时取消**机制
4. 复用 Semaphore 并发控制
5. 复用文件目录结构

## 总体契合度：75%

- 高契合：直接调用、并发控制、状态模型
- 需补充：持久化存储、超时取消