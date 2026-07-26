# Post-Processing Pipeline Design

Source tasks: `feat-260718-01-add-postprocess-pipeline` and `feat-260721-01-postprocess-pipeline`.

This document records durable semantics and constraints. Implementation rounds and audits belong in task records.

## Semantic Update

The 2026-07-21 design replaced two earlier assumptions:

1. Post-processing failure no longer makes the main parsing task `failed`.
2. Rule snapshots are no longer frozen at task creation time.

The current model freezes the run snapshot when a post-processing run is created.

## Scope

Post-processing is an independent phase after the main MinerU parsing task completes.

It:

- Reads the parsed Markdown deliverable.
- Runs one or more configured steps.
- Writes independent Markdown deliverables.
- Does not modify MinerU's original parsing logic.
- Does not overwrite the primary Markdown output.

The LLM configuration is global and OpenAI-compatible through `MINERU_TITLE_*`. The current implementation does not choose a model per task or per plan.

## Three-Layer Model

| Layer | Table | Responsibility |
| --- | --- | --- |
| Action | `postprocess_actions` | Atomic operation. Current type is `llm_transform`; config includes `prompt`, `output_filename`, and optional `context_size`. |
| Plan | `postprocess_plans` | Ordered steps: `[{action_id, output_filename?}]`. A step can override the action output filename. |
| Run | `postprocess_runs` | One execution of a plan against a task. `steps_snapshot` is frozen at run creation. |

Step chaining:

- Step N input = Step N-1 output.
- Re-running with the same output filename overwrites the file.
- Run history is kept, but overwritten files are not historical artifacts.

Trigger sources:

- `auto`: created after parsing output is validated.
- `manual`: created from Admin Console, REST API, or MCP.

## State Separation

Main parsing task status and post-processing run status are independent.

- A task becomes `completed` when parsing completes.
- A post-processing failure does not change the main task status.
- Run statuses are `pending`, `running`, `completed`, `failed`, and `cancelled`.
- CAS transitions are used for claiming, finishing, and cancellation.
- If parsing fails or is cancelled, no auto run is created.

`postprocess_status` exposed to UI/API is derived from the latest run status. Legacy `tasks.postprocess_*` columns are retained for compatibility with existing data, but they are not the primary state model.

## Snapshot and Inheritance

- Run creation freezes the plan/action snapshot.
- Later edits to plans or actions do not affect existing runs.
- Caller default plan is inherited only when both `enable_postprocess` and `postprocess_rule_id` are omitted.
- Explicit `enable_postprocess=False` disables post-processing.
- Explicit `enable_postprocess=True` without a plan is a validation error.
- A disabled or deleted default plan causes inherited creation to fail.

Protection rules:

- Plan referenced by caller defaults: `409 PLAN_REFERENCED_BY_CALLERS`.
- Plan referenced by active tasks/runs: `409 PLAN_IN_USE`.
- Action referenced by plans: `409 ACTION_REFERENCED_BY_PLANS`.

## Runner

- Independent concurrency: `MINERU_POSTPROCESS_MAX_CONCURRENT`, default `2`, range `1-32`.
- Does not consume main parsing concurrency slots.
- Polling scheduler claims pending runs with CAS.
- Blocking LLM calls run outside the event loop.
- Pending runs can be cancelled directly.
- Running runs observe cancellation at chunk/step boundaries.
- On restart, stale `running` runs are moved back to `pending`.

## Context Size

`context_size` is a character budget, not a token budget.

Resolution order:

1. Action config.
2. Task/run default `postprocess_context_size`.
3. Global `MINERU_POSTPROCESS_CONTEXT_SIZE`, default `128 * 1024`, minimum `4096`.

Deployments should set the value well below the actual model context window because prompts, system text, and model output also consume context.

## LLM Error Handling

Transient connection errors are retried with exponential backoff. Read/write timeouts, 4xx responses, invalid JSON, and empty content fail immediately.

Current timeout shape:

```text
connect=10, read=600, write=60, pool=10
```

## Deliverable Contract

Each run step can produce a deliverable with `artifact_type='postprocessed_markdown'`.

The normal access path is:

1. `list_deliverables`
2. `download_deliverable` by `download_key`

All download paths must verify the main task is `completed`; orphan files are not part of the public contract.

---

# 后处理管线设计

来源任务：`feat-260718-01-add-postprocess-pipeline` 与 `feat-260721-01-postprocess-pipeline`。

本文记录长期有效的语义和约束。实现轮次与审计记录应放在任务记录中。

## 语义更新

2026-07-21 的设计替代了两个早期假设：

1. 后处理失败不再导致主解析任务变为 `failed`。
2. 规则快照不再在任务创建时冻结。

当前模型是在创建 post-processing run 时冻结 run 快照。

## 范围

后处理是 MinerU 主解析任务完成后的独立阶段。

它会：

- 读取解析后的 Markdown 交付物。
- 执行一个或多个配置步骤。
- 写入独立 Markdown 交付物。
- 不修改 MinerU 原始解析逻辑。
- 不覆盖主 Markdown 输出。

LLM 配置是全局的，通过 `MINERU_TITLE_*` 指向 OpenAI 兼容服务。当前实现不支持按任务或按方案选择模型。

## 三层模型

| 层 | 表 | 职责 |
| --- | --- | --- |
| Action | `postprocess_actions` | 原子操作。当前类型为 `llm_transform`；config 包含 `prompt`、`output_filename` 和可选 `context_size`。 |
| Plan | `postprocess_plans` | 有序步骤：`[{action_id, output_filename?}]`。步骤可覆盖 action 的输出文件名。 |
| Run | `postprocess_runs` | 某个 plan 针对某个 task 的一次执行。`steps_snapshot` 在 run 创建时冻结。 |

步骤串联：

- 第 N 步输入 = 第 N-1 步输出。
- 使用相同输出文件名重跑会覆盖文件。
- run 历史保留，但被覆盖文件不是历史 artifact。

触发来源：

- `auto`：解析产物验证通过后创建。
- `manual`：通过 Admin Console、REST API 或 MCP 创建。

## 状态分离

主解析任务状态与后处理 run 状态相互独立。

- 解析完成后，任务变为 `completed`。
- 后处理失败不改变主任务状态。
- run 状态为 `pending`、`running`、`completed`、`failed`、`cancelled`。
- 认领、完成和取消使用 CAS 转换。
- 解析失败或取消时，不创建 auto run。

对 UI/API 暴露的 `postprocess_status` 来自最新 run 状态。历史 `tasks.postprocess_*` 列为兼容既有数据而保留，但不再是主要状态模型。

## 快照与继承

- 创建 run 时冻结 plan/action 快照。
- 后续修改 plan 或 action 不影响已有 run。
- 只有同时省略 `enable_postprocess` 和 `postprocess_rule_id` 时，才继承 caller 默认方案。
- 显式 `enable_postprocess=False` 表示禁用后处理。
- 显式 `enable_postprocess=True` 但不传 plan 是校验错误。
- 默认方案被停用或删除后，继承创建会失败。

保护规则：

- plan 被 caller 默认引用：`409 PLAN_REFERENCED_BY_CALLERS`。
- plan 被活跃任务/run 引用：`409 PLAN_IN_USE`。
- action 被 plan 引用：`409 ACTION_REFERENCED_BY_PLANS`。

## Runner

- 独立并发：`MINERU_POSTPROCESS_MAX_CONCURRENT`，默认 `2`，范围 `1-32`。
- 不占用主解析并发槽位。
- 轮询调度器通过 CAS 认领 pending runs。
- 阻塞式 LLM 调用移出事件循环。
- pending run 可直接取消。
- running run 在 chunk/step 边界响应取消。
- 重启后，陈旧 `running` run 会回退到 `pending`。

## Context Size

`context_size` 是字符预算，不是 token 预算。

解析顺序：

1. Action config。
2. Task/run 默认 `postprocess_context_size`。
3. 全局 `MINERU_POSTPROCESS_CONTEXT_SIZE`，默认 `128 * 1024`，下限 `4096`。

部署时应把该值设为显著低于模型实际上下文窗口，因为 prompt、系统文本和模型输出也会占用上下文。

## LLM 错误处理

瞬时连接错误会指数退避重试。Read/write timeout、4xx、非法 JSON 和空内容立即失败。

当前 timeout 形态：

```text
connect=10, read=600, write=60, pool=10
```

## 交付物契约

每个 run step 都可能产生 `artifact_type='postprocessed_markdown'` 的交付物。

正常访问路径是：

1. `list_deliverables`
2. 按 `download_key` 调用 `download_deliverable`

所有下载路径都必须验证主任务为 `completed`；孤儿文件不是公开契约的一部分。
