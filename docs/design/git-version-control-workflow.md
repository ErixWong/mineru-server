# Git 版本控制工作流

## 1. 目标

本规范用于约束当前仓库的日常开发、任务分流和变更提交方式，目标是：

- 让 `master` 保持稳定
- 避免一个分支混做多个主题
- 让每次提交可理解、可回滚、可验证
- 避免依赖目录、构建产物和本地秘密误入版本控制

---

## 2. 主分支约定

### `master`

`master` 是默认稳定分支。

要求：

- 不直接在 `master` 上做功能开发
- 只合入经过验证的稳定增量
- `master` 上的提交应始终具备可发布性或接近可发布性

例外：

- 纯文档微调
- 明确授权的紧急修复

---

## 3. 分支命名规范

统一格式：

```text
{type}/{task-id}-{short-name}
```

例如：

```text
feat/030-admin-console-vue-spa
fix/029-public-mode-safety
refactor/031-remove-legacy-admin-console
docs/031-git-version-control
test/032-admin-ui-smoke-tests
chore/033-ignore-admin-ui-dist
```

### type 取值

- `feat`：新功能
- `fix`：问题修复
- `refactor`：重构
- `docs`：文档
- `test`：测试
- `chore`：杂项工程

### task-id 约定

- 优先使用 `docs/tasks/active/` 中已有任务编号
- 若任务尚未建立，先补任务目录，再创建分支

---

## 4. 一分支一主题

每个分支只处理一个明确主题。

允许：

- 一个功能的前后端改动
- 一个安全问题的完整修复
- 一次结构迁移

不允许：

- 同一分支同时做前端迁移 + 安全修复 + 文档清理
- 为了“顺手”把多个无关主题揉在一起

判断标准：

如果 PR 标题里需要写“以及 / and / plus / 顺手”，通常就说明该拆分了。

---

## 5. 提交信息规范

统一格式：

```text
{type}: 描述
```

例如：

```text
feat: migrate admin console to vue spa
fix: require csrf token for admin writes
refactor: serve admin spa from static dist
docs: add git workflow guide
test: cover admin csrf and upload validation
chore: ignore admin-ui build artifacts
```

### 要求

- 一次提交对应一个清晰增量
- 描述直接说明改了什么
- 不使用模糊消息：
  - `update`
  - `misc`
  - `wip`
  - `tmp`
  - `fix bug`

---

## 6. 提交粒度

推荐粒度是：

- 可独立理解
- 可独立验证
- 可单独回滚

好的例子：

- 一次 trusted proxy 修复
- 一次前端工程骨架搭建
- 一次设置页改密行为修复
- 一次 `.gitignore` 规则补充

坏的例子：

- “把前端、后端、安全、文档都改了”

---

## 7. PR 规范

一个 PR 只解决一个主题。

### PR 标题

直接使用与 commit 类似的格式：

```text
feat: migrate admin console to vue spa
fix: tighten trusted proxy source validation
```

### PR 描述至少应包含

1. 背景
2. 本次改了什么
3. 没改什么
4. 如何验证
5. 风险点或后续事项

---

## 8. 合并前检查

合并到 `master` 前至少检查：

- `git status`
- `git diff --stat`
- `git diff`
- 相关测试是否通过
- 是否带入了不应提交的文件

重点关注：

- 是否误提交 `node_modules/`
- 是否误提交 `dist/`
- 是否误提交 `.env` 或 secrets
- 是否误提交本地调试脚本与缓存目录

---

## 9. 当前项目的特殊规则

### 9.1 前端工程 `mcp-server/admin-ui/`

应提交：

- `package.json`
- `package-lock.json`
- `vite.config.ts`
- `tsconfig*.json`
- `index.html`
- `src/**`

不应提交：

- `node_modules/`
- `dist/`

### 9.2 任务文档 `docs/tasks/`

任务文档用于记录：

- 审计
- 计划
- 验收
- 轮次变更

任务文档可以进入版本控制，但应保持任务边界清晰，不要把任务文档当成代码提交说明的替代品。

### 9.3 设计文档 `docs/design/`

只记录长期有效的设计结论，不记录流水账。

---

## 10. 必须忽略的内容

至少应忽略：

```gitignore
node_modules/
mcp-server/admin-ui/node_modules/
mcp-server/admin-ui/dist/
output/
.env
```

如新增其他本地产物目录，也应同步加入忽略规则。

---

## 11. 推荐工作流

### 开发步骤

1. 从 `master` 切出任务分支
2. 在任务分支内完成单一主题开发
3. 小步提交
4. 运行最小回归验证
5. 提交 PR
6. 审核通过后合并回 `master`

### 示例

当前已存在的典型分支可以是：

```text
feat/030-admin-console-vue-spa
docs/031-git-version-control
test/032-admin-ui-smoke-tests
refactor/033-remove-legacy-admin-console
```

---

## 12. 最小执行规则

如果只保留最关键的 5 条规则，应执行：

1. 不在 `master` 上直接开发功能
2. 一个分支只做一个主题
3. 提交信息使用 `{type}: 描述`
4. 不提交依赖目录、构建产物和 secrets
5. 合并前必须检查 diff 和验证结果

---

## 13. 一句话原则

**`master` 只放稳定代码；所有开发走任务分支；一次分支只做一件事；提交要可回滚；依赖和产物永不入库。**

✌Bazinga！
