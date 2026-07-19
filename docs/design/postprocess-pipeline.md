# 后处理管线设计

来源任务：`feat-260718-01-add-postprocess-pipeline`（round01 建立，round03 定稿语义）。
本文档只记录长期有效的决策与约束，不记录逐轮实现流水账。

## 定位与边界

- 后处理是 MinerU 主解析完成后的第二阶段：读取主 markdown，调用"标题优化 LLM 配置"
  （`MINERU_TITLE_*`）按规则 prompt 清洗，产出独立的 markdown 交付物。
- 不改动 MinerU 原始解析逻辑；不覆盖主 markdown；后处理交付物文件名由规则
  `output_filename` 决定并在任务创建时冻结到任务记录。
- 后处理 LLM 全局唯一，没有按任务/按规则选择模型的能力。

## 双状态机语义（已定案，不得随意变更）

任务主状态与 `postprocess_status` 是两个独立状态机，但失败语义耦合（M1=B）：

- **后处理失败 → 任务整体 `failed`**。后处理属于交付契约的一部分，不允许"任务成功但
  后处理失败"的完成态。日志与 UI 必须能区分失败发生在解析阶段还是后处理阶段。
- `postprocess_status` 枚举：
  | 值 | 含义 |
  |------|------|
  | `not_enabled` | 任务未启用后处理 |
  | `pending` | 已启用，等待执行（解析尚未完成） |
  | `processing` | 后处理执行中 |
  | `completed` | 后处理成功 |
  | `failed` | 后处理阶段自身失败 |
  | `skipped` | 任务在后处理启动前已失败（解析失败），后处理从未启动 |

- 解析失败的两条早退路径（worker 非零退出、必需产物缺失）必须将 `postprocess_status`
  收敛为 `skipped`，禁止滞留 `pending`。

## 规则继承与快照（已定案，M3）

- 任务创建时 `enable_postprocess`/`postprocess_rule_id` 均未传 → 继承调用方默认规则；
  显式 `enable_postprocess=False` → 本次禁用；显式 `True` 但不传 rule → 直接报错
  （不继承，见 `task_service` 校验）。
- 调用方默认规则被删除或停用后，继承路径**继续报错**（强制显式处理，不静默降级）。
- 作为防护：删除规则、或将规则置为停用时，若仍被任一 caller 的
  `default_postprocess_rule_id` 引用（含已禁用 caller），返回 409 拦截。
- 任务创建时将规则的 title/prompt/output_filename 冻结为快照，执行只读快照不回表，
  排队任务不受后续规则更新影响。

## context_size 口径

- 单位为**字符数**（`len(text)`），是送入单个分片的原文预算，不是 token 窗口。
- 切片按预算填满原文；规则 prompt、系统提示、连续性摘要与模型输出额外占用模型窗口。
- 不内置固定比例安全余量（规则 prompt 长度不可预知，固定比例既不透明也不可靠）；
  部署时应将 `MINERU_POSTPROCESS_CONTEXT_SIZE` 设为显著低于模型实际窗口的值。
- 三级解析：任务级值（API/MCP 可传，admin UI 不暴露）→ 全局默认
  `MINERU_POSTPROCESS_CONTEXT_SIZE`（默认 128×1024，下限钳制 4096）。

## 执行约束

- 后处理是同步阻塞 HTTP，必须经 `asyncio.to_thread` 移出事件循环，禁止在 async 路径上直接调用。
- LLM 调用仅对瞬时**连接**错误重试（ConnectError、ConnectTimeout、5xx，至多 2 次、指数退避）；
  Read/Write 超时（确定性超窗 payload）与 4xx/非法 JSON/空内容立即失败。
  超时配置：`httpx.Timeout(connect=10, read=600, write=60, pool=10)`。
- 取消/超时路径：`cancel_task` 置 `threading.Event` 标志；`process_markdown` 分片间检查并抛
  `PostprocessCancelledError`。该异常**不在线程内消化**，直接传播至 `_process_internal` 转为
  `asyncio.CancelledError`，由 `_on_task_done` 统一走取消归类。
- 产物与状态提交顺序：**先写后处理产物文件，后以 processing 守卫提交 completed DB 状态**。
  文件写入失败 → 异常即任务失败，DB 不会出现虚假 completed；
  DB 守卫失败 → 产物为孤儿文件，不构成交付契约。
  `TaskStateService` 的全部终态操作均有 `status = 'processing'` CAS 保护，多个角色竞争时只有一个胜出。
- 所有下载入口（admin、公开 REST、MCP）必须先验证任务主状态为 `completed`；
  孤儿后处理文件不得绕过任务状态门禁被下载。
- 交付物列表中 `postprocessed_markdown` 仅对启用后处理的任务出现
  （以冻结文件名是否存在判定）；admin 与公开 API 两条下载路径都必须使用冻结文件名
  计算允许下载键。
