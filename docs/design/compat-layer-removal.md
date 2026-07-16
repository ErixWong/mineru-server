# 兼容层清理与主路径收敛

## 1. 适用前提

本项目当前尚未正式上线，不存在必须平滑迁移的历史调用方、历史部署或稳定旧契约。

因此本项目当前阶段的原则不是“兼容优先”，而是“主路径定型优先”。

## 2. 核心结论

### 2.1 不为未上线系统保留兼容层

兼容层只在以下前提成立时才有价值：

- 已有外部调用方依赖旧路径
- 已有生产部署依赖旧鉴权方式
- 已有公开契约需要渐进迁移

当前三项均不成立，因此：

- 不保留旧 REST 结果读取路径
- 不保留旧 MCP 工具别名或 deprecated 包装层
- 不保留多套并行认证模式
- 不保留“默认结果读取”这类历史思维入口

### 2.2 对外只保留单一路径

#### REST

- 任务创建：`POST /api/tasks`、`POST /api/uploads`、`POST /api/uploads/submit`、`POST /api/tasks/from-upload`
- 任务查询：`GET /api/tasks/{task_id}`
- 交付物读取：`GET /api/tasks/{task_id}/deliverables`
- 单交付物下载：`GET /api/tasks/{task_id}/deliverables/download?download_key=...`

#### MCP

- `create_task`
- `get_task_status`
- `list_deliverables`
- `download_deliverable`
- `cancel_task`
- `list_tasks`

#### Admin

- 管理台只服务内部控制面
- 写操作继续保留 `same-origin + CSRF`
- HTTPS 与 SSL 终止由反向代理负责，不在应用层做人造兼容判断

## 3. 认证收敛原则

认证层不再为“可能出现的未来接入方式”预留并行模式。

应收敛为一套明确主路径，并删除以下类型的兼容性设计：

- 单用户模式兼容
- 文件映射 API key 模式
- trusted proxy 推断式用户映射
- 旧共享 token 的历史兼容兜底

保留的认证方案必须满足两个条件：

1. 当前主流程真实在用
2. 能直接解释为未来正式上线方案的一部分

## 4. 结果读取收敛原则

结果读取统一围绕 deliverables 模型：

- 先列出交付物
- 再按 `download_key` 读取具体交付物

不再保留“默认结果”“旧 markdown 读取口”“旧 artifact 口”“旧 image 口”等历史兼容入口。

## 5. 本轮删除清单

### 5.1 代码

- 认证多模式兼容分支
- 默认结果兼容入口
- MCP deprecated helper 与残留包装逻辑

### 5.2 文档

- README 中的兼容路径说明
- docs/README 中的旧接口列表与兼容叙事

### 5.3 测试

- 仅服务于 deprecated/compat/legacy 层的测试
- 对已删除旧路径的“仍需验证兼容包装存在”类测试

## 6. 验收标准

- 主 README 与 docs/README 只保留当前主路径
- 运行时代码中不再存在仅为未上线系统服务的兼容层
- 测试聚焦当前主契约，而不是历史兼容残留

## 7. 决策理由

未上线阶段继续保留兼容层，只会带来：

- 代码路径膨胀
- 测试矩阵扩大
- 文档边界模糊
- 认证与接口契约迟迟无法定型

当前最优策略不是“兼容更多”，而是“尽快定型并删除包袱”。

✌Bazinga！
