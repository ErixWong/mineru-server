# GitHub Container Registry 镜像发布

本文档说明 `mineru-server` 如何通过 GitHub Actions 自动构建、发布镜像到 GitHub Container Registry (ghcr.io)，以及旧版本清理策略。

## 镜像地址

```
ghcr.io/erixwong/mineru-server
```

当前只发布 slim 变体（基于 `Dockerfile.slim`）：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

## 工作流说明

### 1. 构建与发布：`docker-publish.yml`

文件位置：`.github/workflows/docker-publish.yml`

触发条件：

- 推送到 `main` / `master` 分支
- 推送 `v*` 标签（如 `v3.4.4`）
- PR 到 `main` / `master`（仅构建，不推送）
- 手动触发 `workflow_dispatch`

构建内容：

- 使用 `Dockerfile.slim` 构建 slim 镜像
- 推送到 `ghcr.io/erixwong/mineru-server`

生成标签：

| 标签 | 说明 |
|---|---|
| `latest-slim` | 默认分支最新构建 |
| `master-slim` / `main-slim` | 分支名 |
| `3.4.4-slim` / `3.4-slim` / `3-slim` | 语义化版本（推送 `v*` 标签时） |
| `<short-sha>-slim` | 提交 SHA |

注意事项：

- 镜像约 7–9 GB，构建时间 5–7 分钟
- GitHub Actions 免费 runner 实际提供约 145 GB 磁盘，足够构建 slim 镜像
- 工作流中已加入 `df -h` 和 `docker system df` 检查，方便排查磁盘问题

### 2. 版本清理：`cleanup-packages.yml`

文件位置：`.github/workflows/cleanup-packages.yml`

触发条件：

- 每周日 UTC 00:00 自动运行
- 手动触发 `workflow_dispatch`

策略：

- 只保留 ghcr.io 中 `mineru-server` 包的最近 3 个版本
- 删除超过 3 个的旧版本（包括带 SHA tag 的版本）
- `latest-slim` 和 `master-slim` 始终指向最新版本，因此会被保留

警告：

- 如果手动为某个旧版本打了重要标签（如 `v1.0.0-slim`），该版本也可能被删除，因为清理只按版本更新时间保留最近 3 个
- 如需长期保留某个版本，需要额外调整清理规则

## 使用镜像

### 直接拉取

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

### 在 docker-compose.yml 中使用

```yaml
services:
  mineru-mcp:
    image: ghcr.io/erixwong/mineru-server:latest-slim
    # 其他配置保持不变
```

## 手动触发

进入 GitHub Actions 页面：

- Docker Publish: https://github.com/ErixWong/mineru-server/actions/workflows/docker-publish.yml
- Cleanup Package Versions: https://github.com/ErixWong/mineru-server/actions/workflows/cleanup-packages.yml

点击 **Run workflow** 即可手动触发。

## 故障排查

### manifest unknown

如果拉取 `latest-slim` 报 `manifest unknown`，说明 `latest-slim` 标签还未生成。可能是：

- 工作流尚未跑完
- 工作流标签配置有误

临时解决方案：先拉分支标签，如 `master-slim`。

### 磁盘空间不足

如果构建失败并报 `no space left on device`：

1. 检查工作流日志中的 `Check disk space before build` 和 `Check disk space after build`
2. 考虑使用 GitHub Larger runner 或 self-hosted runner

## 相关文件

- `.github/workflows/docker-publish.yml`
- `.github/workflows/cleanup-packages.yml`
- `Dockerfile.slim`
- `README.md`（使用 GitHub 预构建镜像说明）
