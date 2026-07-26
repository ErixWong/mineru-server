# Admin Console Design

## Positioning

The Admin Console is an internal control plane for MinerU Server. It is not a commercial billing system, quota platform, or multi-tenant governance suite.

Its current job is to help operators:

- Create and manage caller API keys.
- Disable callers quickly when needed.
- Inspect recent tasks and failures.
- Review deliverables and source files.
- Clone a failed or historical task with adjusted parameters.
- Configure post-processing actions and plans.
- Check runtime settings and diagnostics.

The design intentionally stays small: one internal control plane on top of the existing global task queue.

## Current Entry Points

| Surface | Path | Auth |
| --- | --- | --- |
| Admin SPA | `/admin/*` | Session cookie |
| Admin API | `/api/admin/*` | Session cookie + CSRF + same-origin checks |
| Public REST API | `/api/*` | Bearer caller API key |
| MCP | `/mcp/` | Bearer caller API key |

The historical server-rendered Admin Console is retired. The maintained UI is the Vue SPA under `admin-ui/`.

## Navigation Model

The current product areas are:

| Area | Purpose |
| --- | --- |
| Dashboard | Runtime overview and recent health signals |
| Callers | Caller identity, API key lifecycle, enable/disable, reset/reveal key |
| Tasks | Task list, filters, detail, deliverables, diagnostics, clone/reprocess actions |
| Postprocess Rules/Plans | Action and plan management |
| Settings | Runtime settings, admin profile, password change |

## Caller Model

The project currently combines caller identity and credential management into one domain object. This is sufficient for internal use.

Important properties:

- Each caller has one active API key.
- API keys are encrypted in SQLite.
- Authentication lookup uses a digest/HMAC path instead of decrypting every caller.
- List APIs expose masked key fields only.
- Full key reveal/copy requires an explicit admin action.
- Resetting a key invalidates the old key immediately.
- Disabled or expired callers cannot authenticate public REST/MCP requests.

`MINERU_CALLER_KEY_MASTER_KEY` is required for caller key encryption and reveal. The same database should keep the same master key.

## Task Management

Task views should optimize for operational triage:

- What was submitted?
- Who submitted it?
- Which backend and parameters were used?
- Is the task pending, processing, completed, failed, or cancelled?
- What files were produced?
- What failed, and is it worth cloning with adjusted parameters?

Current task actions:

- View task detail.
- View diagnostics.
- Download source file.
- List/download deliverables.
- Download deliverables archive.
- Cancel active task.
- Clone a task into a new task with copied source file reference and editable parameters.
- Trigger manual post-processing runs for completed tasks.

Task clone is preferred over mutating and re-running the original task. It preserves the original audit trail and creates a new task record.

## Post-Processing Management

Admins manage:

- Atomic actions.
- Ordered plans.
- Manual runs on completed tasks.
- Run cancellation.

Post-processing is independent from the main task state. A completed parsing task remains completed even if a post-processing run fails.

## Current Non-Goals

The current Admin Console does not implement:

- Commercial plans.
- Billing.
- Per-caller quota enforcement.
- Per-caller concurrency slots.
- Multi-key ownership hierarchies.
- A full audit-log product.

These can be added later if usage grows, but they are intentionally outside the current control-plane scope.

## Product Principles

- Optimize for internal operator speed.
- Keep caller management understandable.
- Preserve task history instead of mutating old records.
- Prefer explicit reveal/copy actions for sensitive keys.
- Surface enough diagnostics to fix real failures without turning the UI into a full observability suite.

---

# Admin Console 设计

## 定位

Admin Console 是 MinerU Server 的内部控制面。它不是商业计费系统、配额平台或多租户治理套件。

它当前要帮助运维者：

- 创建和管理 caller API key。
- 必要时快速禁用 caller。
- 查看最近任务和失败情况。
- 查看交付物和源文件。
- 复制失败任务或历史任务，并调整参数后重新提交。
- 配置后处理 action 和 plan。
- 查看运行时设置和诊断信息。

设计刻意保持轻量：在现有全局任务队列之上提供一个内部控制面。

## 当前入口

| 界面 | 路径 | 鉴权 |
| --- | --- | --- |
| Admin SPA | `/admin/*` | Session cookie |
| Admin API | `/api/admin/*` | Session cookie + CSRF + same-origin 检查 |
| 公开 REST API | `/api/*` | Bearer caller API key |
| MCP | `/mcp/` | Bearer caller API key |

历史服务端渲染 Admin Console 已退役。当前维护的 UI 是 `admin-ui/` 下的 Vue SPA。

## 导航模型

当前产品区域：

| 区域 | 用途 |
| --- | --- |
| Dashboard | 运行概览和健康信号 |
| Callers | caller 身份、API key 生命周期、启停、重置/reveal key |
| Tasks | 任务列表、筛选、详情、交付物、诊断、复制/重跑动作 |
| Postprocess Rules/Plans | action 和 plan 管理 |
| Settings | 运行时设置、管理员资料、修改密码 |

## Caller 模型

当前项目把 caller 身份和凭据管理合并为一个领域对象。对内部使用场景来说已经足够。

关键性质：

- 每个 caller 有一个当前有效 API key。
- API key 加密存储在 SQLite。
- 鉴权查询走 digest/HMAC 路径，而不是逐个解密 caller。
- 列表 API 只暴露脱敏 key 字段。
- 完整 key reveal/copy 必须由管理员显式触发。
- 重置 key 后，旧 key 立即失效。
- disabled 或 expired caller 无法通过公开 REST/MCP 鉴权。

`MINERU_CALLER_KEY_MASTER_KEY` 是 caller key 加密和 reveal 的必需配置。同一个数据库应保持同一个 master key。

## 任务管理

任务视图应围绕运维排障优化：

- 提交了什么？
- 谁提交的？
- 使用了哪个 backend 和哪些参数？
- 任务是 pending、processing、completed、failed 还是 cancelled？
- 产出了哪些文件？
- 哪里失败了，是否值得复制一份任务并调整参数重试？

当前任务动作：

- 查看任务详情。
- 查看诊断信息。
- 下载源文件。
- 列出/下载交付物。
- 下载交付物 archive。
- 取消活跃任务。
- 复制任务：引用/复用源文件，调整参数后创建新任务。
- 对已完成任务手动触发后处理 run。

任务复制优先于修改原任务后重跑。这样可以保留原始审计轨迹，并创建新的任务记录。

## 后处理管理

管理员可管理：

- 原子 action。
- 有序 plan。
- 已完成任务上的手动 run。
- run 取消。

后处理与主任务状态独立。解析任务 completed 后，即使后处理 run 失败，主任务仍保持 completed。

## 当前非目标

当前 Admin Console 不实现：

- 商业套餐。
- 计费。
- caller 级配额强制。
- caller 级并发槽位。
- 多 key 归属层级。
- 完整审计日志产品。

如果使用量增长，这些能力可以后续补充，但当前刻意不纳入内部控制面范围。

## 产品原则

- 优化内部运维效率。
- 让 caller 管理保持易懂。
- 保留任务历史，而不是修改旧记录。
- 敏感 key 采用显式 reveal/copy 动作。
- 暴露足够诊断来修复真实失败，但不把 UI 做成完整观测平台。
