# Git Version Control Workflow

## Goal

This workflow keeps daily development, task branches, commits, and pull requests predictable.

The goals are:

- Keep `master` stable.
- Avoid mixing unrelated topics in one branch.
- Make each commit understandable, reversible, and verifiable.
- Prevent dependencies, build artifacts, local caches, and secrets from entering version control.

## Main Branch

`master` is the stable default branch.

Rules:

- Do not do feature development directly on `master`.
- Merge only verified increments.
- `master` should remain releasable or close to releasable.

Exceptions:

- Small documentation-only edits.
- Explicitly approved emergency fixes.

## Branch Naming

Use:

```text
{type}/{task-id}-{short-name}
```

Examples:

```text
feat/260722-01-admin-ui-i18n
fix/260720-01-admin-proxy-cors
refactor/260725-02-flatten-repository-layout
docs/260726-01-docs-bilingual-layout
```

Common `type` values:

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`

Prefer using the task ID from `docs/tasks/active/`. If no task exists and the work is substantial, create one first.

## One Branch, One Topic

A branch should handle one clear topic.

Allowed:

- Frontend and backend changes for one feature.
- A complete fix for one security issue.
- One structural migration.

Avoid:

- Combining frontend migration, security hardening, and documentation cleanup in one branch.
- Adding unrelated "while I am here" changes.

If a PR title needs "and", "plus", or "also", consider splitting it.

## Commit Messages

Use:

```text
{type}: description
```

Examples:

```text
feat: add task clone flow
fix: preserve auth header for mcp slash path
refactor: flatten repository layout
docs: add bilingual docs index
test: cover caller key reset
chore: ignore local env files
```

Avoid vague messages such as:

- `update`
- `misc`
- `wip`
- `tmp`
- `fix bug`

## Pull Requests

One PR should solve one topic.

A useful PR description includes:

1. Background.
2. What changed.
3. What did not change.
4. How it was validated.
5. Risks or follow-up items.

## Pre-Merge Checklist

Before merging to `master`, check:

- `git status`
- `git diff --stat`
- `git diff`
- Relevant tests or builds
- Whether unintended files were staged

Pay special attention to:

- `node_modules/`
- `admin-ui/dist/`
- `.env`
- `output/`
- local debug files
- secrets

## Project-Specific Rules

### `admin-ui/`

Commit:

- `package.json`
- `package-lock.json`
- `vite.config.ts`
- `tsconfig*.json`
- `index.html`
- `src/**`

Do not commit:

- `node_modules/`
- `dist/`

### `docs/tasks/`

Task docs may be versioned, but they are not a substitute for a good commit message or PR description.

### `docs/design/`

Design docs should contain durable decisions, not implementation round logs.

## Minimum Rules

If only five rules are remembered:

1. Do not develop features directly on `master`.
2. Keep one branch to one topic.
3. Use `{type}: description` commit messages.
4. Never commit dependencies, build artifacts, local outputs, or secrets.
5. Check diff and validation before merging.

---

# Git 版本控制工作流

## 目标

本规范用于让日常开发、任务分支、提交和 PR 更可预测。

目标是：

- 让 `master` 保持稳定。
- 避免一个分支混做多个无关主题。
- 让每次提交可理解、可回滚、可验证。
- 避免依赖目录、构建产物、本地缓存和 secrets 进入版本控制。

## 主分支

`master` 是稳定默认分支。

规则：

- 不直接在 `master` 上做功能开发。
- 只合入经过验证的增量。
- `master` 应保持可发布或接近可发布状态。

例外：

- 小型纯文档调整。
- 明确授权的紧急修复。

## 分支命名

使用：

```text
{type}/{task-id}-{short-name}
```

示例：

```text
feat/260722-01-admin-ui-i18n
fix/260720-01-admin-proxy-cors
refactor/260725-02-flatten-repository-layout
docs/260726-01-docs-bilingual-layout
```

常见 `type`：

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`

优先使用 `docs/tasks/active/` 中的任务编号。如果工作较大且还没有任务目录，应先补任务目录。

## 一分支一主题

一个分支只处理一个明确主题。

允许：

- 一个功能的前后端改动。
- 一个安全问题的完整修复。
- 一次结构迁移。

避免：

- 同一分支同时做前端迁移、安全加固和文档清理。
- 顺手加入无关改动。

如果 PR 标题需要写 “and”、“plus”、“also” 或“顺手”，通常应该拆分。

## 提交信息

使用：

```text
{type}: description
```

示例：

```text
feat: add task clone flow
fix: preserve auth header for mcp slash path
refactor: flatten repository layout
docs: add bilingual docs index
test: cover caller key reset
chore: ignore local env files
```

避免模糊信息：

- `update`
- `misc`
- `wip`
- `tmp`
- `fix bug`

## Pull Request

一个 PR 只解决一个主题。

有用的 PR 描述至少包含：

1. 背景。
2. 本次改了什么。
3. 没改什么。
4. 如何验证。
5. 风险或后续事项。

## 合并前检查

合并到 `master` 前检查：

- `git status`
- `git diff --stat`
- `git diff`
- 相关测试或构建
- 是否暂存了不该提交的文件

重点关注：

- `node_modules/`
- `admin-ui/dist/`
- `.env`
- `output/`
- 本地调试文件
- secrets

## 项目特殊规则

### `admin-ui/`

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

### `docs/tasks/`

任务文档可以进入版本控制，但不能替代清晰的 commit message 或 PR 描述。

### `docs/design/`

设计文档应记录长期决策，不记录实现轮次流水。

## 最小规则

如果只记住五条：

1. 不直接在 `master` 上做功能开发。
2. 一个分支只做一个主题。
3. 提交信息使用 `{type}: description`。
4. 永不提交依赖、构建产物、本地产物或 secrets。
5. 合并前检查 diff 和验证结果。
