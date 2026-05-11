# MinerU 数据库表结构设计（无 SQLite）

## 关键发现

MinerU **不使用 SQLite 或任何数据库**。所有任务存储在内存中。

## 内存数据结构

### AsyncParseTask（任务对象）

```python
@dataclass
class AsyncParseTask:
    task_id: str                     # UUID
    status: str                      # pending/processing/completed/failed
    backend: str                     # pipeline/vlm-auto-engine/hybrid-*
    file_names: list[str]            # 解析后的文件名列表
    created_at: str                  # ISO 时间戳
    output_dir: str                  # 输出目录路径
    parse_method: str                # auto/txt/ocr
    lang_list: list[str]             # 语言列表
    formula_enable: bool             # 公式解析开关
    table_enable: bool               # 表格解析开关
    image_analysis: bool             # 图像分析开关
    server_url: Optional[str]        # VLM HTTP 服务 URL
    return_md: bool                  # 返回 Markdown
    return_middle_json: bool         # 返回中间 JSON
    return_model_output: bool        # 返回模型输出
    return_content_list: bool        # 返回内容列表
    return_images: bool              # 返回提取图片
    response_format_zip: bool        # ZIP 格式响应
    return_original_file: bool       # 包含原始文件
    start_page_id: int               # 起始页码
    end_page_id: int                 # 结束页码
    upload_names: list[str]          # 原始上传文件名
    uploads: list[str]               # 上传文件路径列表
    submit_order: int                # 提交顺序（用于排队计算）
    started_at: Optional[str]        # 开始处理时间
    completed_at: Optional[str]      # 完成时间
    error: Optional[str]             # 错误信息
```

### AsyncTaskManager（任务管理器）

```python
class AsyncTaskManager:
    tasks: dict[str, AsyncParseTask]       # 任务字典 {task_id: task}
    task_events: dict[str, asyncio.Event]  # 任务完成事件
    queue: asyncio.Queue[str]              # 任务 ID 队列
    active_tasks: set[asyncio.Task]        # 正在执行的 asyncio.Task
```

## MCP Server 推荐表结构

如果 MCP Server 需要持久化存储，建议使用以下 SQLite 表结构：

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,                 -- UUID
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/processing/completed/failed/cancelled
    backend TEXT NOT NULL,               -- 解析后端类型
    file_names TEXT NOT NULL,            -- JSON array: ["doc1", "doc2"]
    created_at TEXT NOT NULL,            -- ISO timestamp
    started_at TEXT,                     -- ISO timestamp
    completed_at TEXT,                   -- ISO timestamp
    output_dir TEXT NOT NULL,            -- 输出目录路径
    parse_method TEXT NOT NULL DEFAULT 'auto',
    lang_list TEXT NOT NULL,             -- JSON array: ["ch", "en"]
    formula_enable INTEGER NOT NULL DEFAULT 1,
    table_enable INTEGER NOT NULL DEFAULT 1,
    image_analysis INTEGER NOT NULL DEFAULT 1,
    server_url TEXT,                     -- VLM HTTP server URL
    return_options TEXT,                 -- JSON: {md: true, middle_json: false, ...}
    start_page_id INTEGER NOT NULL DEFAULT 0,
    end_page_id INTEGER NOT NULL DEFAULT 99999,
    upload_names TEXT NOT NULL,          -- JSON array: original filenames
    upload_paths TEXT NOT NULL,          -- JSON array: stored file paths
    submit_order INTEGER NOT NULL,       -- FIFO order
    error TEXT,                          -- Error message if failed
    queued_ahead INTEGER DEFAULT 0,      -- Number of tasks ahead in queue
    timeout_seconds INTEGER DEFAULT 3600, -- Task timeout
    created_date TEXT NOT NULL,          -- YYYY-MM-DD for date partitioning
    last_status_update TEXT NOT NULL,    -- Last status change time
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_date ON tasks(created_date);
CREATE INDEX idx_tasks_submit_order ON tasks(submit_order);
CREATE INDEX idx_tasks_status_date ON tasks(status, created_date);
```

## 任务状态流转图

```
           +--------+
           | submit |
           +--------+
               |
               v
          +---------+
          | pending |
          +---------+
               |
        (dispatcher picks)
               |
               v
       +------------+
       | processing |
       +------------+
               |
      +--------+--------+
      |                 |
      v                 v
+-----------+      +-----------+
| completed |      |   failed  |
+-----------+      +-----------+
      |                 |
      +--------+--------+
               |
        (retention timeout)
               |
               v
          +---------+
          | cleaned |
          +---------+
```

## 关键区别对比

| 特性 | MinerU | MCP Server 建议 |
|------|--------|-----------------|
| 存储 | 内存字典 | SQLite 数据库 |
| 持久化 | 无 | 有 |
| 重启恢复 | 任务丢失 | 任务保留 |
| 状态查询 | 内存查找 | SQL 查询 |
| 清理方式 | 时间过期 | 时间过期 + 手动清理 |
| 取消状态 | 无 | 新增 cancelled 状态 |
| 日期分区 | 无 | created_date 字段 |