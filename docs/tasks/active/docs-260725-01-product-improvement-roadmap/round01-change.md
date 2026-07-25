# round01-change

## 范围

本轮开始实施 V1.1「可观测管理台」，完成以下内容：

1. 新增 Admin Dashboard 指标接口；
2. 新增 Admin 配置诊断接口；
3. 优化任务列表筛选体验；
4. 补充前端 Dashboard 页面；
5. 补充中英文 i18n 文案和前端类型；
6. 增加后端契约测试。

## 后端变更

### 新增 `GET /api/admin/dashboard`

返回只读运营指标：

- 队列状态计数：pending、processing、completed、failed、cancelled、total；
- 近 24 小时任务量；
- 近 7 天任务量、完成数、失败数、成功率、失败率；
- 最近完成任务的平均排队耗时和平均解析耗时；
- 后处理 run 状态计数；
- caller 总数、启用数、禁用数、过期数；
- 默认 backend、解析并发、后处理并发；
- 管理员安全状态；
- 最近 5 条失败任务脱敏摘要。

敏感信息控制：

- 不返回完整 caller api key；
- 不返回 `api_key_encrypted`、`api_key_hash`、`api_key_key_id`；
- 不返回 output 绝对路径；
- 不返回异常堆栈。

### 新增 `GET /api/admin/diagnostics`

返回结构化配置检查：

- 默认 backend 是否在白名单；
- 默认 backend 是否需要远程 VLM，以及 VLM 配置是否完整；
- 后处理 LLM 配置是否完整；
- output 目录是否可写；
- database 目录是否可写；
- caller key master key 是否有效；
- Admin 密码是否仍默认或必须修改；
- 单实例部署边界提示。

接口只返回配置状态和修复建议，不回显任何密钥值。

### 扩展 `GET /api/admin/tasks`

新增筛选参数：

- `filename`：文件名模糊匹配；
- `backend`：解析后端筛选；
- `postprocess_status`：按派生后处理状态筛选；
- `stale_processing_minutes`：筛选处理中超过指定分钟数的任务；
- `caller_id=__unassigned__`：筛选未指派任务。

旧参数保持兼容：

- `caller_id`
- `status`
- `start_date`
- `end_date`
- `key`
- `task_id`
- `limit`
- `offset`

## 前端变更

### Dashboard 页面

`DashboardPage.vue` 从欢迎页改为运营首页：

- 顶部 4 个指标卡：任务总数、活跃任务、近 7 天成功率、近 7 天失败率；
- 队列概览表；
- 运行配置表；
- 配置诊断列表；
- 最近失败任务列表；
- 刷新按钮；
- 跳转到失败任务筛选结果。

### 任务列表筛选

`TasksPage.vue` 调整筛选入口：

- caller 从手填 ID 改为下拉；
- 增加未指派任务选项；
- 增加文件名模糊搜索；
- 增加 backend 筛选；
- 增加后处理状态筛选；
- 增加处理中超时筛选；
- 增加快捷按钮：最近失败、处理中超过 10 分钟、今日任务、未指派任务；
- 保留 API key 和 task_id 精确查询。

### 类型和文案

- `types.ts` 新增 Dashboard 和 Diagnostics response 类型；
- `zh-CN.json` / `en.json` 增加 Dashboard、diagnostics、任务筛选相关文案。

## 测试

### 后端

命令：

```powershell
& 'C:\Users\Eric\AppData\Local\Programs\Python\Launcher\py.exe' -3.13 -m pytest tests\test_admin_security.py
```

结果：

```text
23 passed in 92.83s
```

新增覆盖：

- Dashboard 指标可返回；
- Dashboard 不泄露完整 caller key、密文、摘要；
- Diagnostics 能返回结构化检查；
- Diagnostics 不回显 caller key master key；
- 任务列表新增 filename/backend/postprocess/stale/unassigned 筛选可用。

### 前端

命令：

```powershell
npm.cmd run build
```

结果：

```text
vue-tsc --noEmit && vite build
build passed
```

### 空白检查

命令：

```powershell
git diff --check
```

结果：

- 无空白错误；
- Git 提示若干文件 LF 将在下次触碰时替换为 CRLF，未影响检查结果。

## 当前状态

| 项目 | 状态 | 备注 |
|---|---|---|
| Dashboard 指标接口 | `verified` | Admin 契约测试通过 |
| Diagnostics 接口 | `verified` | Admin 契约测试通过 |
| Dashboard 页面 | `verified` | 前端 build 通过 |
| 任务筛选后端 | `verified` | Admin 契约测试通过 |
| 任务筛选前端 | `verified` | 前端 build 通过 |

## 后续建议

V1.1 可以继续拆第二轮：

1. 抽 `AdminMetricsService` / `AdminDiagnosticsService`，降低 `admin_api.py` 体积；
2. 为 Dashboard 增加自动刷新间隔和最近失败任务更多字段；
3. 为 diagnostics 增加 VLM 真实连通性探测，但必须避免泄露密钥和引入慢请求；
4. 为任务筛选增加 URL query 双向同步，方便复制排障链接。
