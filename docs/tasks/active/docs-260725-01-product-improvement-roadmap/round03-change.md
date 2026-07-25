# Round 03：复制任务与可修改参数复跑

## 1. 背景

原路线图中的“可修改参数复跑”如果直接扩展原地 `reprocess`，会带来两个产品问题：

- 原任务的失败记录、产物目录、重试次数和新参数混在一起，后续排障成本更高；
- 用户已经倾向于“复制一份任务再改参数”，这更符合审计和对比分析习惯。

因此本轮将能力收敛为：**从历史任务复制出一个新任务，并允许在创建副本时修改解析参数**。

## 2. 产品决策

复制任务时，上传文件采用**物理复制**，不引用旧任务文件。

原因：

- 新任务生命周期独立，旧任务删除或清理不会影响副本；
- 新任务目录仍保持现有输出契约，排障时不需要跨目录追溯源文件；
- 避免引入引用计数、共享文件清理、跨任务权限校验等复杂治理；
- 小体积 PDF 场景下，额外存储成本低于生命周期耦合成本。

复制任务不会复制旧任务的解析产物、错误日志、后处理 run 记录。

## 3. 实现范围

### 3.1 后端

新增 Admin API：

- `POST /api/admin/tasks/{task_id}/clone`

请求体支持覆盖：

- `backend`
- `lang`
- `formula_enable`
- `table_enable`
- `image_analysis`
- `server_url`
- `start_page_id`
- `end_page_id`
- `enable_postprocess`
- `postprocess_rule_id`
- `postprocess_context_size`
- `caller_id`
- `inherit_caller`

默认行为：

- 未显式传入的解析参数继承原任务；
- `inherit_caller=true` 时继承原任务 caller；
- `inherit_caller=false` 且不传 caller 时，新任务归属 `admin-console`；
- 指定 caller 时校验 caller 存在、未禁用、未过期；
- 源文件不存在时返回 `SOURCE_NOT_FOUND`。

### 3.2 前端

任务详情页新增“复制任务”入口和弹窗：

- 默认从任务诊断参数回填；
- 支持修改 backend、语言、页码范围、公式/表格/图片分析开关；
- 支持选择继承调用方、不指派或指定调用方；
- 支持选择是否启用后处理及后处理方案；
- 创建成功后跳转到新任务详情。

任务列表页新增轻量快捷入口：

- 行操作增加“详情 / 复制 / 删除”；
- 列表“复制”按原参数直接创建副本；
- 创建成功后跳转到新任务详情；
- 需要修改参数时，进入详情页使用“复制任务”弹窗。

失败任务详情页新增推荐动作：

- 错误卡片中优先展示“复制并修改参数”；
- 原地“重新处理”仍保留，用于失败任务原样重跑。

## 4. 验收

已通过：

- `py -3.13 -m pytest tests\test_admin_security.py`
  - 27 passed
- `npm run build`
- `git diff --check`
  - 仅 Windows CRLF 提示，无 whitespace error

新增测试覆盖：

- 复制任务会生成新的 task_id；
- 新任务目录中存在独立复制的 PDF 源文件；
- 可覆盖 backend、语言、页码、识别开关、caller 归属；
- 旧任务产物不会被复制到新任务目录；
- 原始文件缺失时返回 `SOURCE_NOT_FOUND`。

## 5. 后续建议

- 后续如需节省存储，可单独设计内容寻址文件池，但不建议在当前单机 SQLite 产品阶段提前引入。
