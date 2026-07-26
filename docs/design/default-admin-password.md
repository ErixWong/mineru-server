# Default Admin Password Decision

## Problem

The current `admin123` fallback behaves as an initial bootstrap password only:

- It is used only when the admin account is created for the first time.
- It does not overwrite the admin password in an existing `tasks.db`.

This means:

- Empty database: the admin user's initial password is `admin123`, or the value of `MINERU_ADMIN_INITIAL_PASSWORD`.
- Existing database: the existing password is preserved.

## Options

### Option A: Initial Value Only

- The default password is used only at first initialization.
- Existing deployments are not reset by code updates.
- This is the current implementation.

### Option B: Reset to Default When Env Is Missing

- If `MINERU_ADMIN_INITIAL_PASSWORD` is missing, reset the admin password to `admin123`.
- This gives stronger consistency for new deployments.
- It requires extra startup logic and creates a risk of surprising existing deployments.

## Decision

Use Option A: initial value only.

Reasons:

1. Avoid unexpected password changes in existing deployments.
2. Improve safety: production should use an explicit strong password, not a default.
3. Keep startup behavior simple and predictable.

## Operations Guidance

1. Production: set a strong `MINERU_ADMIN_INITIAL_PASSWORD`.
2. First deployment: if the default password is used, log in and change it immediately.
3. Existing deployment: if password reset is required, update it intentionally through SQL or delete/recreate the admin user with care.

## Decision Date

2026-07-16

---

# 默认管理员密码行为决策

## 问题

当前 `admin123` 回退值只作为首次初始化密码：

- 仅在首次创建 admin 账户时使用。
- 不会覆盖已有 `tasks.db` 中的管理员密码。

这意味着：

- 空数据库：admin 用户初始密码为 `admin123`，或 `MINERU_ADMIN_INITIAL_PASSWORD` 的值。
- 已有数据库：保持原有密码不变。

## 选项

### 选项 A：仅首次初始化默认值

- 默认密码只在首次初始化时使用。
- 代码更新不会重置已有部署。
- 当前实现采用该策略。

### 选项 B：环境变量缺失时重置为默认值

- 如果缺少 `MINERU_ADMIN_INITIAL_PASSWORD`，则把 admin 密码重置为 `admin123`。
- 新部署一致性更强。
- 需要额外启动逻辑，并且可能意外影响已有部署。

## 决策

采用选项 A：仅首次初始化默认值。

理由：

1. 避免已有部署被意外改密。
2. 更安全：生产环境应显式设置强密码，而不是依赖默认值。
3. 启动行为更简单、可预测。

## 运维建议

1. 生产环境：设置强 `MINERU_ADMIN_INITIAL_PASSWORD`。
2. 首次部署：如果使用默认密码，登录后立即修改。
3. 已有部署：如需重置密码，应通过 SQL 或谨慎删除/重建 admin 用户来显式处理。

## 决策日期

2026-07-16
