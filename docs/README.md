# Documentation

This directory contains supporting documentation for MinerU Server. The root [README.md](../README.md) is the primary project entry point and the source of truth for current startup commands, public API paths, MCP tools, authentication, and runtime configuration.

## Layout Assessment

The current `docs/` tree is useful, but it had a few maintainability issues:

- Current product docs, design decisions, task logs, and historical drafts were easy to confuse.
- Several files still described older paths or earlier architecture assumptions.
- Some long MinerU research notes looked like current product contracts even though they are mainly background material.
- `docs/tasks/active/` contains some completed work records; these should be archived periodically, but task history should not be rewritten just to make it bilingual.
- Most current docs were Chinese-only, while the root README is now bilingual.

This update keeps the existing directory shape, but makes the boundary clearer:

- Maintained docs get bilingual navigation or bilingual content.
- Historical records stay historical and receive explicit status labels.
- The root README remains the canonical operational contract.

## Directory Map

```text
docs/
+-- README.md                  # This documentation index
+-- python-package.md          # Python package notes
+-- deployment/                # Deployment and image publishing docs
+-- design/                    # Long-lived design decisions
+-- mineru/                    # MinerU backend, model, and engine notes
+-- tasks/                     # Task records: active and archived
+-- archive/                   # Early drafts and retired documentation
```

## Reading Order

For most users:

1. Start with [../README.md](../README.md).
2. Use [deployment/README.md](deployment/README.md) for image/deployment topics.
3. Use [mineru/README.md](mineru/README.md) for backend and model behavior.
4. Use [design/README.md](design/README.md) for durable product and architecture decisions.

For maintainers:

1. Keep new maintained docs bilingual when practical.
2. Add a bilingual status note to research or historical documents that are not current contracts.
3. Leave `docs/tasks/` task logs as internal work records; they are not part of the public documentation bilingual pass.
4. Move completed records from `docs/tasks/active/` to `docs/tasks/archived/` only during a separate task-history cleanup.

## Current Contract Summary

| Area | Current source of truth |
| --- | --- |
| Startup commands | [../README.md](../README.md) |
| REST API public paths | [../README.md](../README.md) |
| MCP tools | [../README.md](../README.md) |
| Authentication model | [../README.md](../README.md), [design/auth-mode-hard-switch.md](design/auth-mode-hard-switch.md) |
| Admin Console behavior | [../README.md](../README.md), [design/admin-management-console.md](design/admin-management-console.md) |
| Docker images and GHCR | [deployment/github-packages.md](deployment/github-packages.md) |
| Backend/model notes | [mineru/models-and-backends.md](mineru/models-and-backends.md) |

## Bilingual Documentation Policy

- Current entry docs should be bilingual, with English first and Chinese after.
- Short decision docs should be fully bilingual.
- Long research notes may use bilingual summaries plus a clear status note.
- Task logs and archive files do not need full translation unless they become maintained reference docs.
- Code snippets, environment variable names, paths, and API examples should stay identical across languages.

---

# 文档说明

本目录保存 MinerU Server 的辅助文档。根目录 [README.md](../README.md) 是项目主入口，也是当前启动命令、公开 API 路径、MCP tools、鉴权和运行时配置的事实来源。

## 布局评估

当前 `docs/` 目录有价值，但存在几类维护问题：

- 当前产品文档、设计决策、任务流水和历史草稿边界不够清楚。
- 部分文件还保留旧路径或早期架构假设。
- 一些长篇 MinerU 研究笔记看起来像当前产品契约，但实际上更偏背景材料。
- `docs/tasks/active/` 里有部分已经完成的工作记录；这些应该周期性归档，但不应为了双语化而重写历史流水。
- 多数当前文档原本只有中文，而根 README 已经改成双语。

这次调整不大改目录形状，而是把边界说清楚：

- 维护型文档提供双语导航或双语正文。
- 历史记录保持历史属性，并补充明确状态说明。
- 根 README 继续作为当前运行和接口契约的主文档。

## 目录地图

```text
docs/
+-- README.md                  # 当前文档索引
+-- python-package.md          # Python 包说明
+-- deployment/                # 部署与镜像发布文档
+-- design/                    # 长期设计决策
+-- mineru/                    # MinerU backend、模型与推理引擎说明
+-- tasks/                     # 任务记录：active 与 archived
+-- archive/                   # 早期草稿与退役文档
```

## 推荐阅读顺序

普通使用者：

1. 先读 [../README.md](../README.md)。
2. 部署与镜像问题读 [deployment/README.md](deployment/README.md)。
3. backend 和模型行为读 [mineru/README.md](mineru/README.md)。
4. 产品和架构决策读 [design/README.md](design/README.md)。

维护者：

1. 新增维护型文档时尽量保持双语。
2. 研究或历史文档如果不是当前契约，应补双语状态说明。
3. `docs/tasks/` 任务流水保留为内部工作记录，不纳入公开文档双语化范围。
4. 只有在单独做任务历史清理时，才把完成记录从 `docs/tasks/active/` 移到 `docs/tasks/archived/`。

## 当前契约摘要

| 范围 | 当前事实来源 |
| --- | --- |
| 启动命令 | [../README.md](../README.md) |
| REST API 公开路径 | [../README.md](../README.md) |
| MCP tools | [../README.md](../README.md) |
| 鉴权模型 | [../README.md](../README.md), [design/auth-mode-hard-switch.md](design/auth-mode-hard-switch.md) |
| Admin Console 行为 | [../README.md](../README.md), [design/admin-management-console.md](design/admin-management-console.md) |
| Docker 镜像与 GHCR | [deployment/github-packages.md](deployment/github-packages.md) |
| Backend/模型说明 | [mineru/models-and-backends.md](mineru/models-and-backends.md) |

## 双语文档策略

- 当前入口文档应使用双语，英文在前，中文在后。
- 短篇决策文档应尽量完整双语。
- 长篇研究笔记可以采用双语摘要加明确状态说明。
- 任务流水和 archive 历史文件不要求完整翻译，除非后续升级为维护型参考文档。
- 代码片段、环境变量名、路径和 API 示例在双语版本中保持一致。
