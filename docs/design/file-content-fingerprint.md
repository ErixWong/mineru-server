# 文件内容指纹（file_hash）设计

维护型设计参考，记录"提交文件计算内容 hash 并落库"的长期决策。实现轮次见 `docs/tasks/active/feat-260802-01-file-hash-dedup/`。

## 决策摘要

- 每个任务入库时记录输入文件的 SHA-256 内容指纹（`tasks.file_hash`）与字节数（`tasks.file_size`），作为后续去重、审计的基础数据。
- hash 在**写入文件的同时流式计算**（写代理拦截 `write_bytes` / `open("wb")`），不二次读盘；对 500MB 上限文件约 1–2s，相对解析耗时可忽略。
- 计算注入点**唯一**：REST / MCP / Admin 上传 / Admin 克隆四条创建路径全部汇聚到 `TaskService._create_task_with_writer`，在此包装 `input_writer` 即全覆盖。
- 历史任务 `file_hash` 为 NULL 属正常状态，**不做回填**（回填需全量读盘，收益低）。
- schema 版本：v15 引入 `file_hash TEXT`、`file_size INTEGER` 两列与 `idx_tasks_file_hash` 索引；旧库经 `ALTER TABLE` 迁移，新库在基线建表。

## 写代理的 fail-fast 设计（重要约束）

`_HashingPath` / `_HashingFile`（`services/task_service.py`）的写入拦截语义：

- **拦截**：`write_bytes` 与二进制写模式 `open("wb"/"ab"/"xb"/含"+"的写模式)` —— 每次 `write` 同步更新 sha256 与字节数。
- **透传**：读模式（如 `open("rb")`）—— 不产生写入，不计入 hash。
- **fail-fast**：未覆盖的写入入口直接报错——`write_text`、文本写模式 `open("w"/"a"/"x"/"+" 无 b)` 均 raise `AttributeError`。

意图：若未来新增 writer 使用其它写入 API，直接报错，而不是静默绕过散列计算。否则会出现"落盘内容与 file_hash 不一致"的数据完整性隐患——hash 仍记了但文件写入走了未拦截通道，去重键失效。

约束：任何新增的 `input_writer` 必须走被拦截的二进制写入 API，或在代理中显式扩展散列拦截。

核心不变量（有测试锁定）：**落库 `file_hash` 必须等于任务目录中实际落盘文件内容的 sha256**——`test_hash_matches_on_disk_content` 系列读回落盘文件比对，防"hash 记了但文件写偏"的静默失效。

## 去重键（与事项 3 的边界）

本轮只落库指纹，不实现去重。事项 3 的去重键定为：

```
file_hash + backend + lang + start_page_id + end_page_id
+ formula_enable + table_enable + image_analysis
（http-client 后端再含有效 server_url）
```

后处理参数不进去重键——复用的是"解析产物"，后处理 run 各任务独立执行。`file_size` 可用于 hash 比对前的廉价预筛。
