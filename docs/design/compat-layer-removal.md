# Compatibility Layer Removal

## Scope

This project has not yet promised a stable public production contract for legacy clients. Because of that, the codebase should converge on clear primary paths instead of preserving multiple compatibility layers.

## Core Decision

Do not keep compatibility layers for retired pre-release behavior unless there is a concrete deployed caller that must be migrated.

This applies to:

- Old authentication modes.
- Old REST result-reading paths.
- Deprecated MCP tool aliases.
- Historical Admin Console pages.

## Current Primary Paths

### REST

- Create task: `POST /api/tasks`
- Query task: `GET /api/tasks/{task_id}`
- List deliverables: `GET /api/tasks/{task_id}/deliverables`
- Download deliverable: `GET /api/tasks/{task_id}/deliverables/download?download_key=...`
- Cancel task: `DELETE /api/tasks/{task_id}`

### MCP

- `create_task`
- `get_task_status`
- `list_deliverables`
- `download_deliverable`
- `cancel_task`
- `list_tasks`
- Post-processing helpers where documented by the root README

### Admin

- Admin SPA: `/admin/*`
- Admin API: `/api/admin/*`
- Auth model: session cookie + CSRF token + same-origin checks

## Authentication Principle

Public REST/MCP access uses caller API keys from the database:

```text
Authorization: Bearer <caller_api_key>
```

The old `MCP_HTTP_AUTH_TOKEN` environment variable is not a supported authentication mode.

## Result-Reading Principle

Deliverables are the primary result contract. Callers should list deliverables first and then download by `download_key`.

Images are part of the same deliverables model.

## Acceptance Criteria

- New docs describe only the current primary path.
- Tests cover the current path rather than legacy wrappers.
- Deprecated code should be removed when no current caller depends on it.
- Historical docs must be clearly labeled as archive or reference material.

---

# 兼容层清理与主路径收敛

## 适用范围

本项目尚未向历史调用方承诺稳定的公开生产契约。因此，代码库应收敛到明确主路径，而不是长期保留多套兼容层。

## 核心决策

除非存在必须迁移的真实部署调用方，否则不为预发布阶段退役行为保留兼容层。

适用范围包括：

- 旧鉴权模式。
- 旧 REST 结果读取路径。
- deprecated MCP tool 别名。
- 历史 Admin Console 页面。

## 当前主路径

### REST

- 创建任务：`POST /api/tasks`
- 查询任务：`GET /api/tasks/{task_id}`
- 列出交付物：`GET /api/tasks/{task_id}/deliverables`
- 下载交付物：`GET /api/tasks/{task_id}/deliverables/download?download_key=...`
- 取消任务：`DELETE /api/tasks/{task_id}`

### MCP

- `create_task`
- `get_task_status`
- `list_deliverables`
- `download_deliverable`
- `cancel_task`
- `list_tasks`
- 根 README 中记录的后处理辅助工具

### Admin

- Admin SPA：`/admin/*`
- Admin API：`/api/admin/*`
- 鉴权模型：session cookie + CSRF token + same-origin 检查

## 鉴权原则

公开 REST/MCP 访问使用数据库 caller API key：

```text
Authorization: Bearer <caller_api_key>
```

旧的 `MCP_HTTP_AUTH_TOKEN` 环境变量不再是支持的鉴权模式。

## 结果读取原则

Deliverables 是当前主要结果契约。调用方应先列出 deliverables，再按 `download_key` 下载。

图片也属于同一套 deliverables 模型。

## 验收标准

- 新文档只描述当前主路径。
- 测试覆盖当前路径，而不是历史包装层。
- 没有当前调用方依赖时，应移除 deprecated 代码。
- 历史文档必须明确标记为 archive 或 reference。
