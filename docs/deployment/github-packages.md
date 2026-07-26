# GitHub Container Registry Publishing

This document explains how `mineru-server` publishes Docker images to GitHub Container Registry (`ghcr.io`) and how old image versions are cleaned up.

## Image

```text
ghcr.io/erixwong/mineru-server
```

The current published variant is the slim image based on `Dockerfile.slim`:

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

## Workflow: `docker-publish.yml`

File:

```text
.github/workflows/docker-publish.yml
```

Triggers:

- Push to `main` or `master`.
- Push a `v*` tag, such as `v3.4.4`.
- Pull request to `main` or `master`; build only, no push.
- Manual `workflow_dispatch`.

Build behavior:

- Builds with `Dockerfile.slim`.
- Pushes to `ghcr.io/erixwong/mineru-server`.

Generated tags:

| Tag | Meaning |
| --- | --- |
| `latest-slim` | Latest default branch build |
| `master-slim` / `main-slim` | Branch tag |
| `3.4.4-slim` / `3.4-slim` / `3-slim` | Semantic version tags from `v*` |
| `<short-sha>-slim` | Commit SHA tag |

Notes:

- The slim image is still large, roughly 7-9 GB.
- GitHub-hosted runners currently provide enough disk for the slim build.
- The workflow includes disk checks to help troubleshoot build failures.

## Workflow: `cleanup-packages.yml`

File:

```text
.github/workflows/cleanup-packages.yml
```

Triggers:

- Weekly schedule.
- Manual `workflow_dispatch`.

Policy:

- Keep the latest 3 package versions.
- Delete older versions, including SHA-tagged versions.
- Moving tags such as `latest-slim` and `master-slim` continue to point at the newest version.

Warning: an older important version can still be deleted if the cleanup rule is based only on recency. Adjust the workflow before relying on long-term retention.

## Use the Image

Pull directly:

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

Use in Compose:

```yaml
services:
  mineru-mcp:
    image: ghcr.io/erixwong/mineru-server:latest-slim
```

## Troubleshooting

### `manifest unknown`

The tag has not been published yet, or the publishing workflow did not create it. Check the workflow run first. A temporary workaround is to pull a branch tag such as `master-slim`.

### `no space left on device`

Check the workflow disk-space steps. If the image grows, move to a larger or self-hosted runner.

---

# GitHub Container Registry 镜像发布

本文说明 `mineru-server` 如何发布 Docker 镜像到 GitHub Container Registry (`ghcr.io`)，以及旧镜像版本如何清理。

## 镜像

```text
ghcr.io/erixwong/mineru-server
```

当前发布的是基于 `Dockerfile.slim` 的 slim 变体：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

## 工作流：`docker-publish.yml`

文件：

```text
.github/workflows/docker-publish.yml
```

触发条件：

- 推送到 `main` 或 `master`。
- 推送 `v*` 标签，例如 `v3.4.4`。
- PR 到 `main` 或 `master`；只构建，不推送。
- 手动 `workflow_dispatch`。

构建行为：

- 使用 `Dockerfile.slim` 构建。
- 推送到 `ghcr.io/erixwong/mineru-server`。

生成标签：

| 标签 | 含义 |
| --- | --- |
| `latest-slim` | 默认分支最新构建 |
| `master-slim` / `main-slim` | 分支标签 |
| `3.4.4-slim` / `3.4-slim` / `3-slim` | 来自 `v*` 的语义化版本标签 |
| `<short-sha>-slim` | 提交 SHA 标签 |

说明：

- slim 镜像仍然较大，约 7-9 GB。
- GitHub hosted runner 当前磁盘足够构建 slim 镜像。
- 工作流包含磁盘检查步骤，便于排查构建失败。

## 工作流：`cleanup-packages.yml`

文件：

```text
.github/workflows/cleanup-packages.yml
```

触发条件：

- 每周定时。
- 手动 `workflow_dispatch`。

策略：

- 保留最近 3 个 package version。
- 删除更旧版本，包括 SHA tag 版本。
- `latest-slim`、`master-slim` 等移动标签继续指向最新版本。

注意：如果清理规则只按更新时间保留版本，较旧的重要版本仍可能被删除。需要长期保留前，应先调整 workflow。

## 使用镜像

直接拉取：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim
```

在 Compose 中使用：

```yaml
services:
  mineru-mcp:
    image: ghcr.io/erixwong/mineru-server:latest-slim
```

## 故障排查

### `manifest unknown`

说明该 tag 还没有发布，或发布 workflow 没有创建它。先检查 workflow run。临时方案是拉取分支标签，例如 `master-slim`。

### `no space left on device`

检查 workflow 中的磁盘空间步骤。如果镜像继续变大，应改用更大的 runner 或 self-hosted runner。
