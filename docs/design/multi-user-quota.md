# 多用户门户与页数预充值额度设计

本文记录 issue #43 第 1～4 期落地的账号、额度、接口与兼容约定，是当前实现的设计参考。

## 账号模型

- `users` 是门户登录账号；账号使用共享的 `/api/admin/login` 登录，凭据通过 `admin_session` cookie 建立 session。
- 每个门户用户绑定且仅绑定一个 `caller`。用户创建时生成一个 API key，明文只在创建响应中返回一次，数据库中保存加密值及用于鉴权的摘要。
- 门户 session 用于按 `user_id` 隔离门户读取；关联 caller 的 API key 用于现有公开 REST API/MCP 鉴权。两种身份最终映射到同一用户和 caller 任务归属。
- `role=user` 只能使用门户能力，不能访问管理员 API；`role=admin` 使用管理台并可管理用户和额度。

## 页数额度模型

- 额度单位是实际参与解析的页数，不是请求数、文件数或货币金额。
- `callers.quota_total_pages` 表示累计预充值页数；`NULL` 表示不限量。新用户初始为 `NULL`，未充值前仍是不限量；首次充值后成为有限页数额度。
- 余额由最近一条 `quota_ledger.balance_after` 表示；若有限额度尚无流水，则余额等于总充值量。充值、任务预扣、结算调整及返还均写入台账，并在事务中更新。
- 创建任务时先根据输入文件及 `start_page_id` / `end_page_id` 估算参与解析的页数，再原子预扣。额度不足时不创建任务并返回 `403 QUOTA_EXCEEDED`。
- 任务成功后以可获得的实际页数结算；若实际页数少于预扣数，写入正向 `task_settlement_adjustment` 返还差额，若较多则写入负向调整。
- 失败、取消和超时任务返还全部预扣页数，写入正向 `task_release`。返还幂等，已结算或已返还的任务不会重复入账。
- 不关联 caller 的任务不参与 caller 额度扣减；不限量 caller 跳过余额限制并继续保持 `NULL` 余额。

### 页数估算与结算边界

- PDF 页数优先由 PDFium 读取，估算值为文件实际页数与所选页码范围的交集；PDFium 不可用或文件无法读取时，退化为每 100 KB 向上估一页。
- 非 PDF 输入按所选范围是否包含第 0 页估算为 1 页或 0 页。
- 成功任务实际结算页数的来源依次为：`middle_json` 的 `pdf_info` 页数、`content_list` 中唯一 `page_idx` 数量、任务预扣页数。没有可用产物时以预扣数作为实际数，不额外调整。
- dedup 复用已完成任务产物时，按源任务产物页数优先结算，其次使用源任务 `pages_billed`，最后回退到当前任务预扣页数；复用不会免除当前任务的额度结算。

## 错误语义

`QUOTA_EXCEEDED` 是 HTTP 403，返回标准错误字段以及 `remaining_pages`、`requested_pages`。门户提交接口会附加便于用户理解的提示；余额不够时任务不会进入队列，额度也不会发生变化。

## API 一览

管理和门户 API 共用 `/api/admin/login` 的 session cookie。写操作需要 same-origin 与 CSRF 校验。管理员用户管理 API 仅接受 `admin` 角色；门户 API 仅允许 `user` 或 `admin` 角色并按当前用户限制任务读取。

| 方法 | 路径 | 能力 / 鉴权 |
| --- | --- | --- |
| `POST` | `/api/admin/login` | 管理员或门户用户登录并建立共享 session |
| `GET` | `/api/portal/me` | 当前用户资料和余额；session |
| `GET` | `/api/portal/quota/ledger` | 当前用户额度流水；session |
| `GET` | `/api/portal/tasks` | 当前用户任务列表；session |
| `GET` | `/api/portal/tasks/{task_id}` | 当前用户任务状态；非本人任务也返回 404；session |
| `POST` | `/api/portal/tasks` | 门户 session 上传并提交任务；session + CSRF |
| `GET` | `/api/portal/tasks/{task_id}/result` | 读取本人任务 Markdown；session |
| `GET` | `/api/portal/tasks/{task_id}/deliverables` | 列出本人任务交付物；session |
| `GET` | `/api/portal/tasks/{task_id}/deliverables/download` | 下载本人任务交付物；session |
| `GET` / `POST` | `/api/admin/users` | 管理员列出用户，或创建用户及关联 caller/API key；管理员 session / CSRF |
| `PATCH` | `/api/admin/users/{user_id}` | 管理员修改用户资料、状态、角色或重置密码；管理员 session + CSRF |
| `POST` | `/api/admin/users/{user_id}/quota` | 管理员充值正整数页数；管理员 session + CSRF |
| `GET` | `/api/admin/users/{user_id}/quota/ledger` | 管理员查看用户额度流水；管理员 session |
| `POST` | `/api/tasks` | 关联 caller 的 API key 通过既有公开 REST 接口提交任务并触发额度预扣 |

## 兼容策略

- 存量 caller 的 `user_id` 保持 `NULL`，不自动创建门户用户、不改变现有 API key 鉴权和任务访问语义。
- `quota_total_pages = NULL` 的现有 caller 保持不限量；只有显式充值后才转为有限页数。
- 门户用户通过唯一关联 caller 复用现有 API key、caller 配置、任务归属和额度台账，不另建一套任务额度账本。
- 没有关联 user 的 API key 调用方仍可按既有公开 REST/MCP 路径使用服务。

## 非目标

本设计只管理解析页数的预充值与消耗，不包含支付、货币定价、商业套餐、发票或账单。配额强制按解析页数执行，不扩展为通用资源计量系统。
