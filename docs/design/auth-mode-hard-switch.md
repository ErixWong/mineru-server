# 认证模式硬切换决策

## 变更背景

本项目认证已从旧的 `MCP_HTTP_AUTH_TOKEN` 环境变量模式切换为数据库 caller key 模式。此变更的核心驱动：

- **安全性提升**：每个 caller 拥有独立 API key，支持独立禁用
- **可审计性**：caller 访问记录可追溯 (`last_used_at`)
- **过期管理**：支持 API key 过期时间设置

## 已完成的迁移

| 项目 | 状态 |
|------|------|
| docker-compose.yml MCP_HTTP_AUTH_TOKEN | 已移除 |
| config.py http_auth_token 字段 | 已删除 |
| auth.py 认证实现 | 已完全迁移至数据库 caller key 模式 |
| 测试用例 | 仅保留当前主路径所需验证 |

## 向后兼容性说明

- 旧的 `MCP_HTTP_AUTH_TOKEN` 模式不再提供兼容层，也不再出现在当前部署说明中
- 如需访问 HTTP / MCP 入口，需通过 admin console 创建 caller 并使用其 API key

## 后续行动项

- [ ] 更新部署文档，说明新认证模式的使用方法
- [ ] 提供 caller API key 的 bootstrap 脚本
- [ ] 持续检查示例配置与镜像说明，避免旧 token 说明回流

## 决策日期

2026-07-16

✌Bazinga！
