# 后处理管线设计

来源任务：`feat-260718-01-add-postprocess-pipeline`（初版），`feat-260721-01-postprocess-pipeline`（三层模型重构定稿）。
本文档只记录长期有效的决策与约束，不记录逐轮实现流水账。

> **语义变更声明**：本文 2026-07-21 版本取代旧版两项已定案语义——
> ① "后处理失败 → 任务整体 failed" 的双状态机耦合语义；② "任务创建时冻结规则快照"。
> 新语义见下（三层模型 / 状态彻底分离 / run 创建时冻结快照）。

## 定位与边界

- 后处理是 MinerU 主解析完成后的独立阶段：读取解析产物 markdown，经流水线处理后产出独立
  markdown 交付物。不改动 MinerU 原始解析逻辑；不覆盖主 markdown。
- 后处理 LLM 全局唯一（`MINERU_TITLE_*`，OpenAI 兼容服务），没有按任务/按方案选择模型的能力。

## 三层模型（已定案）

| 层 | 表 | 职责 |
|----|----|------|
| Action（原子动作） | `postprocess_actions` | 最小处理单元。`type='llm_transform'`，config 含 `prompt` / `output_filename` / `context_size`（可空）。预留类型扩展 |
| Plan（方案/流水线） | `postprocess_plans` | 有序步骤列表 `[{action_id, output_filename?}]`，步骤级可覆盖动作的输出文件名 |
| Run（执行实例） | `postprocess_runs` | 一次方案对一个任务的执行。创建时冻结 `steps_snapshot`（自包含，不回表） |

- 步骤**串联传递**：第 N 步输入 = 第 N-1 步输出文件。
- 重跑**同名覆盖写**（幂等）；历史 run 记录保留但旧产物不可回溯。
- 触发双通道：创建任务时声明（`trigger_source='auto'`）+ 详情页/API 手动（`'manual'`），
  一个任务可挂任意多个 run。

## 状态分离语义（已定案，取代旧双状态机）

- **解析完成即任务 `completed`**。后处理失败不影响任务主状态。
- run 独立状态机：`pending / running / completed / failed / cancelled`，全部 CAS 转换
  （`claim_postprocess_run` / `finish_postprocess_run` / `cancel_pending_postprocess_run`）。
- 解析失败/取消时不产生 auto run（run 在解析产出验证通过后才创建），
  因此不再需要旧模型 `skipped` 语义与 `postprocess_status` 协调代码。
- 对外展示的 `postprocess_status` 是**派生值**：最新 run 的 status
  （admin 面 `running`→`processing` 映射保持前端枚举兼容），无 run 时回退 tasks 列原值。
- `tasks` 表旧 postprocess_* 列（含 `postprocess_status`、三个快照列）永久保留只读，
  不再写入（`enable_postprocess` / `postprocess_rule_id`(=plan_id) / `postprocess_context_size` 除外）。

## 快照与继承（已定案）

- **run 创建时**冻结步骤快照（`build_plan_steps_snapshot`）：方案/动作后续修改不影响已创建的 run。
  （取代旧"任务创建时冻结"语义。）
- caller 默认方案：创建任务时 `enable_postprocess`/`postprocess_rule_id` 均未传 → 继承
  `default_postprocess_rule_id`（值即 plan_id，字段名保留不改）；显式 `False` → 禁用；
  显式 `True` 不传 plan → 报错。默认方案被删除/停用后继承路径继续报错。
- 防护：plan 删除/停用时被 caller 默认引用 → 409 `PLAN_REFERENCED_BY_CALLERS`；
  plan 被活跃任务引用 → 409 `PLAN_IN_USE`；action 被 plan 引用时删除/停用 →
  409 `ACTION_REFERENCED_BY_PLANS`。
- v11 数据迁移：每条历史 rule 生成**同 ID** action + 同 ID 单步 plan，
  `tasks.postprocess_rule_id` 与 caller 默认引用零改写直达。

## 执行器（PostprocessRunner）

- 独立并发信号量 `MINERU_POSTPROCESS_MAX_CONCURRENT`（默认 2，范围 1-32），
  **不占解析并发槽位**（LLM 调用是 IO 密集）。
- 轮询调度（1s）+ CAS 认领；LLM 同步调用经 `asyncio.to_thread` 移出事件循环。
- 取消：pending 直接 CAS 取消；running 置 `threading.Event`，分片边界生效（步骤 cancelled/skipped）。
- 重启恢复：`running` 的 run 回退 `pending` 重新认领（覆盖写保证幂等）。
- runner 单例随应用 lifespan 装配并注入 `TaskProcessor`；API 层取不到实例时退回临时实例
  （create_run 与 pending 取消是纯 DB 操作）。

## context_size 口径（沿用）

- 单位为**字符数**（`len(text)`），是送入单个分片的原文预算，不是 token 窗口。
- 三级解析：action config 值 → 创建任务/触发时的 default（`postprocess_context_size`）→
  全局默认 `MINERU_POSTPROCESS_CONTEXT_SIZE`（默认 128×1024，下限钳制 4096）。
- 不内置固定比例安全余量；部署时应设为显著低于模型实际窗口的值。

## LLM 调用约束（沿用）

- 仅对瞬时**连接**错误重试（ConnectError、ConnectTimeout、5xx，至多 2 次、指数退避）；
  Read/Write 超时与 4xx/非法 JSON/空内容立即失败。
- 超时配置：`httpx.Timeout(connect=10, read=600, write=60, pool=10)`。

## 交付物契约

- run 每步产物都是交付物：`list_deliverables` 聚合该任务全部 run 快照中的
  `output_filename`（去重）+ 历史 `tasks.postprocess_output_filename` 列兜底，
  统一 `artifact_type='postprocessed_markdown'`，走 `download_key` 主路径。
- 所有下载入口必须先验证任务主状态为 `completed`；孤儿文件不构成交付契约。
