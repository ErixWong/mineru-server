# GitHub Container Registry Publishing

This document explains how `mineru-server` publishes Docker images to GitHub Container Registry (`ghcr.io`) and how old image versions are cleaned up.

## Image

```text
ghcr.io/erixwong/mineru-server
```

The published variants are the slim images based on `Dockerfile.slim`, in two torch flavors:

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda   # CUDA torch, ~7-9 GB
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cpu    # CPU-only torch, ~4.5-6 GB
```

`latest-slim` is kept as an alias of `latest-slim-cuda` for backward compatibility.

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

- Builds with `Dockerfile.slim` in a two-flavor matrix (`cpu` / `cuda`).
- The `cpu` flavor preinstalls CPU-only torch via the `TORCH_INDEX_URL` build arg; the `cuda` flavor uses the PyPI default (CUDA) torch.
- Pushes to `ghcr.io/erixwong/mineru-server`.
- On default-branch pushes, `latest-slim` is additionally tagged as an alias of `latest-slim-cuda`.

Generated tags (per flavor; `<flavor>` is `cpu` or `cuda`):

| Tag | Meaning |
| --- | --- |
| `latest-slim-<flavor>` | Latest default branch build of that flavor |
| `latest-slim` | Alias of `latest-slim-cuda` (backward compatibility) |
| `master-slim-<flavor>` / `main-slim-<flavor>` | Branch tag |
| `3.4.4-slim-<flavor>` / `3.4-slim-<flavor>` / `3-slim-<flavor>` | Semantic version tags from `v*` |
| `<short-sha>-slim-<flavor>` | Commit SHA tag |

Notes:

- The cuda image is roughly 7-9 GB; the cpu image is roughly 4.5-6 GB.
- Both flavors run the same backends; the cpu flavor only loses GPU acceleration for local OCR stages (hybrid/pipeline backends). Remote VLM (`*-http-client`) is unaffected.
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
- Moving tags such as `latest-slim`, `latest-slim-cuda` and `master-slim-cuda` continue to point at the newest version.

Warning: an older important version can still be deleted if the cleanup rule is based only on recency. Adjust the workflow before relying on long-term retention.

## Use the Image

Pull directly (choose the flavor matching your host):

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda   # GPU host
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cpu    # CPU-only host
```

Use in Compose:

```yaml
services:
  mineru-mcp:
    image: ${MINERU_IMAGE:-ghcr.io/erixwong/mineru-server:latest-slim-cuda}
```

The repository `docker-compose.yml` uses this GHCR image by default. Override
`MINERU_IMAGE` when testing a local or private image tag.

## Troubleshooting

### `manifest unknown`

The tag has not been published yet, or the publishing workflow did not create it. Check the workflow run first. A temporary workaround is to pull a branch tag such as `master-slim-cuda`.

### `no space left on device`

Check the workflow disk-space steps. If the image grows, move to a larger or self-hosted runner.

---

# GitHub Container Registry 镜像发布

本文说明 `mineru-server` 如何发布 Docker 镜像到 GitHub Container Registry (`ghcr.io`)，以及旧镜像版本如何清理。

## 镜像

```text
ghcr.io/erixwong/mineru-server
```

当前发布的是基于 `Dockerfile.slim` 的 slim 变体，分两种 torch flavor：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda   # CUDA torch，约 7-9 GB
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cpu    # 仅 CPU torch，约 4.5-6 GB
```

`latest-slim` 保留为 `latest-slim-cuda` 的别名，用于向后兼容。

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

- 使用 `Dockerfile.slim`，按 `cpu` / `cuda` 双 flavor 矩阵构建。
- `cpu` flavor 通过 `TORCH_INDEX_URL` 构建参数预装 CPU 版 torch；`cuda` flavor 使用 PyPI 默认（CUDA）torch。
- 推送到 `ghcr.io/erixwong/mineru-server`。
- 默认分支推送时，额外将 `latest-slim` 标记为 `latest-slim-cuda` 的别名。

生成标签（按 flavor；`<flavor>` 为 `cpu` 或 `cuda`）：

| 标签 | 含义 |
| --- | --- |
| `latest-slim-<flavor>` | 该 flavor 的默认分支最新构建 |
| `latest-slim` | `latest-slim-cuda` 的别名（向后兼容） |
| `master-slim-<flavor>` / `main-slim-<flavor>` | 分支标签 |
| `3.4.4-slim-<flavor>` / `3.4-slim-<flavor>` / `3-slim-<flavor>` | 来自 `v*` 的语义化版本标签 |
| `<short-sha>-slim-<flavor>` | 提交 SHA 标签 |

说明：

- cuda 镜像约 7-9 GB，cpu 镜像约 4.5-6 GB。
- 两种 flavor 支持的后端完全相同；cpu flavor 仅失去本地 OCR 阶段（hybrid/pipeline 后端）的 GPU 加速，远程 VLM（`*-http-client`）不受影响。
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
- `latest-slim`、`latest-slim-cuda`、`master-slim-cuda` 等移动标签继续指向最新版本。

注意：如果清理规则只按更新时间保留版本，较旧的重要版本仍可能被删除。需要长期保留前，应先调整 workflow。

## 使用镜像

直接拉取（按主机情况选择 flavor）：

```bash
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cuda   # 有 GPU 的主机
docker pull ghcr.io/erixwong/mineru-server:latest-slim-cpu    # 无 GPU 的主机
```

在 Compose 中使用：

```yaml
services:
  mineru-mcp:
    image: ${MINERU_IMAGE:-ghcr.io/erixwong/mineru-server:latest-slim-cuda}
```

## 故障排查

### `manifest unknown`

说明该 tag 还没有发布，或发布 workflow 没有创建它。先检查 workflow run。临时方案是拉取分支标签，例如 `master-slim-cuda`。

### `no space left on device`

检查 workflow 中的磁盘空间步骤。如果镜像继续变大，应改用更大的 runner 或 self-hosted runner。
