# Authentication Mode Hard Switch

## Background

The project has moved from the old `MCP_HTTP_AUTH_TOKEN` environment-variable model to database-backed caller API keys.

The change was made for three reasons:

- Security: each caller has an independent API key and can be disabled independently.
- Auditability: caller usage can be tracked through fields such as `last_used_at`.
- Lifecycle management: caller keys can expire and be reset.

## Completed Migration

| Item | Status |
| --- | --- |
| `MCP_HTTP_AUTH_TOKEN` in `docker-compose.yml` | Removed |
| `http_auth_token` in `config.py` | Removed |
| Authentication implementation in `auth.py` | Migrated to database caller key mode |
| Tests | Kept only for the current primary path |

## Compatibility Decision

- The old `MCP_HTTP_AUTH_TOKEN` mode no longer has a compatibility layer.
- Current deployment docs should not mention the old token mode as an available option.
- Public REST API and MCP access must use caller API keys created in the Admin Console.

## Follow-Up Items

- Keep deployment examples aligned with caller API key authentication.
- Add or maintain bootstrap tooling only if local setup requires it.
- Continue checking examples and image docs to prevent the old token mode from returning.

## Decision Date

2026-07-16

---

# 认证模式硬切换决策

## 背景

项目认证已从旧的 `MCP_HTTP_AUTH_TOKEN` 环境变量模式切换为数据库 caller API key 模式。

变更原因有三个：

- 安全性：每个 caller 拥有独立 API key，可独立禁用。
- 可审计性：caller 使用情况可通过 `last_used_at` 等字段追踪。
- 生命周期管理：caller key 支持过期和重置。

## 已完成迁移

| 项目 | 状态 |
| --- | --- |
| `docker-compose.yml` 中的 `MCP_HTTP_AUTH_TOKEN` | 已移除 |
| `config.py` 中的 `http_auth_token` | 已移除 |
| `auth.py` 认证实现 | 已迁移到数据库 caller key 模式 |
| 测试 | 仅保留当前主路径验证 |

## 兼容性决策

- 旧的 `MCP_HTTP_AUTH_TOKEN` 模式不再提供兼容层。
- 当前部署文档不应把旧 token 模式写成可用选项。
- 公开 REST API 和 MCP 入口必须使用 Admin Console 创建的 caller API key。

## 后续事项

- 保持部署示例与 caller API key 鉴权一致。
- 只有本地初始化确实需要时，才补充或维护 bootstrap 工具。
- 持续检查示例配置和镜像说明，避免旧 token 模式回流。

## 决策日期

2026-07-16
