# round02-change

## 范围

本轮开始实施 V1.2「任务诊断与交付物工作台」的第一阶段，完成：

1. 新增单任务诊断接口；
2. 新增 Admin 交付物 zip 打包下载；
3. 任务详情页新增诊断视图；
4. 任务详情页交付物列表改为类型分组；
5. 补充前端类型与中英文文案；
6. 增加后端契约测试。

## 后端变更

### 新增 `GET /api/admin/tasks/{task_id}/diagnostics`

返回管理端诊断信息：

- 请求参数：backend、lang、页码范围、公式/表格/图片分析开关、后处理开关；
- `server_url_configured` 仅返回是否配置，不返回 server URL 明文；
- 时间线：created、started、completed、postprocess started/finished；
- 耗时拆解：排队耗时、解析耗时、后处理耗时、总耗时；
- 错误归因：validation、backend_config、timeout、postprocess_error、mineru_error、system_error、none；
- 输出校验：缺失必需产物、推荐产物、可选产物；
- 最近 20 条 task logs 摘要。

安全口径：

- 不返回 API key、caller key 密文、摘要或 key id；
- 不返回 `server_url` 明文；
- 不返回 output 绝对路径；
- 不返回异常堆栈。

### 新增 `GET /api/admin/tasks/{task_id}/deliverables/archive`

将当前任务已暴露的交付物打包为 zip：

- 仅对 `completed` 任务可用；
- 复用 `FileManager.get_allowed_download_keys()` 的白名单；
- zip 内路径按类型分组：
  - `markdown/`
  - `json/`
  - `images/`
  - `attachments/`
- 同名文件自动追加序号；
- 路径全部由安全文件名生成，不使用用户传入路径作为 zip 路径；
- 响应带 `Cache-Control: no-store`。

## 前端变更

### 任务诊断视图

`TaskDetailPage.vue` 新增「任务诊断」卡片：

- 请求参数表；
- 识别能力摘要；
- 是否配置远程 VLM；
- 是否启用后处理；
- 耗时拆解；
- 错误分类 badge；
- 诊断建议；
- 输出缺失摘要；
- 最近日志摘要。

### 交付物工作台

交付物区域从单一分页列表调整为分组展示：

- Markdown；
- JSON；
- 图片；
- 其他。

新增「下载全部」按钮，指向 Admin zip 打包接口。

### 类型和文案

- `types.ts` 新增 `TaskDiagnosticsResponse`；
- `zh-CN.json` / `en.json` 增加任务诊断、耗时、错误分类、交付物分组等文案。

## 测试

### 后端

命令：

```powershell
& 'C:\Users\Eric\AppData\Local\Programs\Python\Launcher\py.exe' -3.13 -m pytest tests\test_admin_security.py
```

结果：

```text
25 passed in 51.98s
```

新增覆盖：

- 单任务 diagnostics 返回请求、输出校验和日志；
- diagnostics 不返回 `server_url` 明文；
- deliverables archive 返回 zip；
- zip 包含 Markdown、JSON、图片；
- zip 不包含未暴露的隐藏任务文件。

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
- Git 仍提示部分文件 LF 将在下次触碰时替换为 CRLF，未影响检查结果。

## 当前状态

| 项目 | 状态 | 备注 |
|---|---|---|
| 任务诊断接口 | `verified` | Admin 契约测试通过 |
| 任务详情诊断卡片 | `verified` | 前端 build 通过 |
| 交付物 zip 下载 | `verified` | Admin 契约测试通过 |
| 交付物分组展示 | `verified` | 前端 build 通过 |

## 后续建议

V1.2 后续可以继续拆：

1. 失败任务「带参数复跑」弹窗；
2. 图片画廊模式和批量图片预览；
3. JSON 结果复制按钮；
4. 复制 REST/MCP 调用示例；
5. 后端抽 `TaskDiagnosticsService` 和 `DeliverableArchiveService`，避免 `admin_api.py` 继续膨胀。
