# 产品优化实施计划

## 1. 使用方式

本计划是产品优化路线图，不是一次性开发清单。每个阶段开始前应拆成独立任务目录，并为实际代码变更补充：

- 需求目标；
- 交互方案；
- API / schema 变化；
- 数据迁移方案；
- 测试计划；
- 验收记录；
- 不能本轮完成的风险和延期项。

状态枚举建议沿用仓库现有任务文档口径：

- `pending`：未开始；
- `in-progress`：实施中；
- `fixed-unverified`：已完成代码或文档变更，尚未完整验证；
- `verified`：完成并通过验收；
- `deferred`：明确延期。

## 2. 当前基线

### 2.1 已具备能力

| 模块 | 当前状态 | 证据入口 |
|---|---|---|
| 任务提交与查询 | REST / MCP / Admin 均可创建或查询异步任务 | `mcp-server/src/mineru_mcp/api.py`、`server.py`、`admin_api.py` |
| 交付物 | Markdown、JSON、图片、后处理产物已进入 deliverables 模型 | `mcp-server/src/mineru_mcp/models.py` |
| Admin SPA | Vue 管理台已覆盖 caller、tasks、postprocess、settings | `mcp-server/admin-ui/src/views/` |
| caller key | 已具备加密存储、脱敏列表、显式 reveal/copy | `admin_api.py`、`caller_key_crypto.py` |
| 后处理 | Action / Plan / Run 三层模型已存在 | `postprocess_runner.py`、`PostprocessRulesPage.vue` |
| 调度 | SQLite 队列、并发、恢复、后处理 runner 已存在 | `task_queue/`、`app.py` |

### 2.2 主要缺口

| 缺口 | 影响 | 建议优先级 |
|---|---|---|
| Dashboard 只是欢迎页 | 管理员无法快速判断系统状态 | P0 |
| 任务筛选偏工程字段 | 排障效率低，非开发用户难用 | P0 |
| 任务详情诊断不足 | 失败任务难定位，复跑策略有限 | P0 |
| 交付物缺少批量下载和分组体验 | 解析结果可取但不够顺手 | P1 |
| caller 缺少配额、backend 范围和审计 | 多调用方场景难治理 | P1 |
| 后处理缺少模板、试运行和版本 | 高价值能力还未产品化 | P2 |
| 文档编码体验不稳定 | Windows 用户首次阅读体验差 | P0 小修 |

## 3. 阶段 V1.1：可观测管理台

### 3.1 Dashboard 指标

**目标**

把 `DashboardPage.vue` 从欢迎页升级为运营首页。

**建议功能**

- 队列概览：pending、processing、completed、failed、cancelled；
- 近 24 小时 / 近 7 天任务量；
- 成功率和失败率；
- 平均排队耗时、平均解析耗时；
- 后处理 pending/running/failed；
- 最近失败任务列表；
- 当前默认 backend、解析并发、后处理并发；
- 默认 Admin 密码、安全配置风险提示。

**建议后端**

- 新增 `GET /api/admin/dashboard`;
- 或先复用 `/api/admin/tasks`、`/api/admin/callers`、`/api/admin/settings/runtime`，前端聚合 MVP；
- 正式版建议抽 `AdminMetricsService`，避免 Dashboard SQL 散落在 router。

**验收条件**

- 空数据库、只有成功任务、存在失败任务、存在运行中任务时页面都能正常展示；
- 不泄露完整 API key、密文、摘要、output 绝对路径或异常堆栈；
- 页面刷新不产生高频重查询；
- 后端测试覆盖指标计算；
- 前端 `npm run build` 通过。

### 3.2 配置健康诊断

**目标**

让管理员能直接看到当前配置是否支持默认工作流。

**建议检查项**

- `MINERU_DEFAULT_BACKEND` 是否在白名单；
- 默认 backend 若为 `*-http-client`，VLM server / api key / model 是否完整；
- 后处理 LLM 配置是否完整；
- `MINERU_OUTPUT_ROOT` 是否可写；
- `MINERU_DB_PATH` 父目录是否可写；
- caller key master key 是否有效；
- 是否仍使用默认 Admin 密码；
- 当前是否为单实例部署假设。

**建议后端**

- 新增 `GET /api/admin/diagnostics`;
- 返回结构化 `checks[]`，字段包括 `key`、`status`、`severity`、`message`、`action_hint`。

**验收条件**

- 不返回任何密钥原文；
- 错误信息能指导管理员修复；
- 健康检查失败不影响普通 `/health` liveness 口径；
- 测试覆盖配置完整、配置缺失和路径不可写。

### 3.3 任务筛选优化

**目标**

把任务页从工程查询面板升级为排障入口。

**建议功能**

- caller 下拉选择，替代手填 caller_id；
- 文件名模糊搜索；
- backend 筛选；
- 后处理状态筛选；
- 快捷筛选：最近失败、处理中超过 10 分钟、今日任务、未指派任务；
- 默认日期范围仍保留最近一周；
- 支持刷新按钮和保留当前筛选条件。

**建议后端**

- 扩展 `GET /api/admin/tasks` 参数：
  - `caller_id`
  - `filename`
  - `backend`
  - `postprocess_status`
  - `stale_processing_minutes`
- 保持旧参数兼容。

**验收条件**

- 旧 URL 参数继续可用；
- 所有新增筛选均有后端测试；
- 前端筛选控件在移动端不重叠；
- 空结果、加载中和错误状态可读。

## 4. 阶段 V1.2：任务诊断与交付物工作台

### 4.1 任务详情诊断视图

**目标**

让任务详情页能解释“任务发生了什么”。

**建议功能**

- 请求参数完整展示：backend、lang、页码范围、formula/table/image 开关、server_url 是否使用；
- 时间线：created、started、completed、postprocess started/finished；
- 耗时拆解：排队、解析、后处理；
- 错误分类：validation、backend_config、vlm_timeout、mineru_error、postprocess_error、system_error；
- 失败任务建议动作：修改 backend 后复跑、禁用后处理复跑、查看配置诊断；
- task_logs 展示最近日志摘要。

**建议后端**

- 扩展 `GET /api/admin/tasks/{task_id}` 的 admin-only 字段；
- 或新增 `GET /api/admin/tasks/{task_id}/diagnostics`。

**验收条件**

- 历史任务缺少字段时 graceful fallback；
- 不泄露敏感 server_url token、API key 或本地绝对路径；
- 失败原因分类有单元测试；
- 详情页自动刷新不覆盖用户正在查看的预览弹窗。

### 4.2 可修改参数复跑

**目标**

失败后不只“原样重跑”，而是允许管理员修正参数后复跑。

**本轮产品决策**

采用“复制任务并修改参数”的方式实现，不直接扩展原任务原地重跑。复制任务会物理复制原始上传文件到新任务目录，不引用旧任务文件；旧任务产物、错误日志和后处理 run 不复制。

**建议功能**

- 任务详情复制弹窗；
- 可修改 backend、lang、页码范围、后处理开关、后处理 plan；
- 可选择继承原调用方、不指派或指定调用方；
- 创建成功后跳转到新任务详情；
- 原地 `reprocess` 保留现有“失败任务原样重跑”语义。

**建议后端**

- 新增 `POST /api/admin/tasks/{task_id}/clone`;
- body 支持可选覆盖参数；
- 创建副本时复用 TaskService 创建路径，保持参数校验与任务目录契约一致。

**验收条件**

- 任意历史任务可复制，源文件缺失时返回明确错误；
- 参数验证与新建任务一致；
- 新任务拥有独立输入文件；
- 复制后旧 key/owner 权限保持正确；
- 不复制旧产物和旧后处理 run。

### 4.3 交付物工作台

**目标**

让结果获取体验接近“工作台”，而不是文件列表。

**建议功能**

- 按类型分组：主 Markdown、后处理 Markdown、JSON、图片、源文件；
- 一键下载全部 zip；
- 图片画廊；
- Markdown 内图片点击预览；
- JSON 格式化、复制；
- 复制 REST 下载示例；
- 复制 MCP tool 调用示例。

**建议后端**

- 新增 `GET /api/admin/tasks/{task_id}/deliverables/archive`；
- public API 后续可考虑同样支持 zip，但 admin 优先。

**验收条件**

- zip 仅包含当前任务允许暴露的交付物；
- download_key 路径穿越测试通过；
- 大量图片时分页或虚拟滚动可用；
- 图片预览不拉取完整 base64 列表。

## 5. 阶段 V1.3：调用方治理

### 5.1 caller 详情页

**目标**

让 caller 成为可运营对象。

**建议功能**

- caller 基本信息、状态、过期时间、默认后处理；
- 近 7 / 30 天任务趋势；
- 成功率、失败率、平均耗时；
- 最近任务；
- 最近 key 操作审计；
- 快捷操作：禁用、重置 key、复制 key、更新默认后处理。

**建议后端**

- 新增 `GET /api/admin/callers/{caller_id}`;
- 新增 `GET /api/admin/callers/{caller_id}/tasks`;
- 新增 `GET /api/admin/callers/{caller_id}/metrics`。

**验收条件**

- disabled / expired caller 页面清晰显示不可认证；
- reveal/copy 仍必须显式点击；
- 详情接口不返回完整 key、密文、摘要、key id。

### 5.2 配额和 backend 白名单

**目标**

减少 caller 滥用风险，并支持不同调用方不同能力。

**建议字段**

- `daily_task_quota`;
- `monthly_task_quota`;
- `max_file_size_mb`;
- `max_page_count`;
- `allowed_backends`;
- `allow_postprocess`;
- `default_lang`。

**建议实现**

- 数据库新增 caller policy 字段或独立 `caller_policies` 表；
- TaskService 创建任务时统一校验；
- Admin UI 提供默认策略和 caller 覆盖策略。

**验收条件**

- REST、MCP、Admin 指派 caller 创建任务时口径一致；
- 超配额返回稳定错误码；
- 默认策略缺省时保持现有行为；
- 策略变更不影响历史任务读取权限。

### 5.3 审计日志

**目标**

关键管理动作可追踪。

**建议记录**

- caller create/update/disable/delete；
- key reveal/reset；
- task delete/reprocess/reassign；
- postprocess plan/action create/update/delete；
- admin login/logout/password change。

**安全要求**

- 审计日志不得记录完整 API key、密文、摘要、密码或 prompt 中的敏感变量；
- 只记录 actor、action、target、metadata、created_at、ip/user-agent 摘要。

**验收条件**

- 审计日志接口分页；
- 敏感字段有测试断言；
- 删除 caller 不删除审计记录。

## 6. 阶段 V1.4：后处理产品化

### 6.1 内置模板

**目标**

降低用户创建后处理 Action/Plan 的门槛。

**建议模板**

- 标题层级优化；
- 全文摘要；
- 合同条款提取；
- 表格解释；
- 图片说明整理；
- 章节重排；
- 双语术语表。

**实现建议**

- 模板以代码或 JSON 文件保存；
- 首次启动可选择初始化；
- Admin UI 支持“从模板创建动作/方案”。

**验收条件**

- 模板不会覆盖用户已有同名方案；
- 模板 prompt 版本可追踪；
- 模板中不内置真实密钥或私有 URL。

### 6.2 Prompt 试运行

**目标**

让管理员保存前能验证 prompt 效果。

**建议功能**

- 从历史任务选择一段 Markdown；
- 手动粘贴样本文本；
- 设置 context_size；
- 展示输入片段、输出结果、耗时、错误；
- 试运行不写入正式 deliverables，除非用户确认保存。

**验收条件**

- LLM 未配置时有清晰提示；
- 试运行可取消；
- 失败不污染正式 run；
- 不把试运行内容写入普通任务产物目录。

### 6.3 Plan 版本管理

**目标**

解决 Plan 修改后历史任务和 caller 默认引用语义不清的问题。

**建议设计**

- Plan 有 draft / published；
- Run 冻结 `plan_version_snapshot`;
- caller 默认引用 published version；
- 删除/禁用 Plan 前显示影响范围；
- 支持复制一个 Plan 成新版本。

**验收条件**

- 历史 run 可看到当时使用的版本；
- 修改 draft 不影响已发布默认方案；
- caller 默认方案不会指向不可执行版本。

## 7. 文档和首次启动体验

### 7.1 UTF-8 文档体验

**问题**

Windows PowerShell 默认编码下中文 README 可能显示乱码，影响首次阅读和排障。

**建议**

- 新增 `.editorconfig`，指定 `charset = utf-8`；
- 新增或检查 `.gitattributes`，确保 Markdown 以 UTF-8 文本处理；
- README 增加 PowerShell 7 或 `Get-Content -Encoding utf8` 提醒；
- CI 增加简单脚本检查 Markdown 是否为 UTF-8。

**验收条件**

- 根 README、docs README、任务文档在 PowerShell UTF-8 读取正常；
- 不引入 BOM 或混合编码；
- 文档链接仍可用。

### 7.2 快速跑通路径

**建议文档**

- 5 分钟本地 pipeline 跑通；
- hybrid-http-client 配置向导；
- 创建 caller 并 curl 调用；
- MCP 客户端配置示例；
- 常见错误对照表。

**验收条件**

- 新用户按文档能完成一次从上传到下载 Markdown 的闭环；
- 未配置 VLM 时不会默认走失败路径；
- 文档明确区分 pipeline、remote VLM、本地 VLM。

## 8. 推荐拆分任务

建议按以下任务继续推进：

1. `feat-260725-01-admin-dashboard-metrics`
   - Dashboard 指标和最近失败任务；
   - 配套 `AdminMetricsService`。
2. `feat-260725-02-admin-diagnostics`
   - 配置健康检查；
   - 管理台风险提示。
3. `feat-260725-03-task-search-and-diagnostics`
   - 任务筛选优化；
   - 任务详情诊断视图。
4. `feat-260725-04-deliverables-workbench`
   - 交付物分组、zip 下载、图片画廊。
5. `feat-260725-05-caller-governance`
   - caller 详情、配额、backend 白名单。
6. `feat-260725-06-admin-audit-log`
   - 管理动作审计日志。
7. `feat-260725-07-postprocess-templates-and-preview`
   - 后处理模板、试运行、版本管理的第一阶段。
8. `docs-260725-02-onboarding-and-encoding`
   - UTF-8 文档体验和快速跑通指南。

## 9. 风险与约束

| 风险 | 说明 | 应对 |
|---|---|---|
| SQLite 单实例边界 | 当前队列和 session 更适合单实例 | 文档明确，扩容另开设计 |
| 指标查询拖慢管理台 | Dashboard 统计可能扫描 tasks | 增加索引、限制时间窗、必要时缓存 |
| 敏感信息泄露 | 诊断和审计容易误带 key / 路径 / 错误堆栈 | response allowlist + 测试断言 |
| 后处理模板质量不稳定 | prompt 模板会影响用户结果信任 | 模板版本化、试运行、默认禁用高风险模板 |
| 复跑污染历史产物 | 修改参数复跑可能覆盖旧产物 | 明确清理/保留策略，记录 retry 快照 |

## 10. 当前状态

| 项目 | 状态 | 备注 |
|---|---|---|
| 产品分析落盘 | `verified` | 本目录保存分析结论和路线图 |
| V1.1 Dashboard | `verified` | 已实现 Dashboard 指标、最近失败任务和基础风险提示 |
| V1.1 Diagnostics | `verified` | 已实现 `/api/admin/diagnostics` 和管理台展示 |
| V1.2 任务诊断 | `verified` | 已实现任务诊断视图和脱敏请求参数 |
| V1.2 交付物工作台 | `verified` | 已实现分组展示、预览和 zip 下载 |
| V1.2 复制任务 | `verified` | 已实现复制任务并修改参数，源文件物理复制 |
| V1.3 caller 治理 | `pending` | 需要 schema 设计 |
| V1.4 后处理产品化 | `pending` | 需要交互设计和模板评审 |
| 文档编码和 onboarding | `pending` | 低成本高收益 |
