# Deployment Docs

Deployment docs describe image publishing, Docker variants, and platform-specific deployment notes. The root [README.md](../../README.md) remains the current quick-start source of truth.

## Maintained Docs

| Document | Purpose |
| --- | --- |
| [github-packages.md](github-packages.md) | GitHub Container Registry publishing and cleanup policy |
| [local-gpu-vlm-pitfalls.md](local-gpu-vlm-pitfalls.md) | Known pitfalls & fixes for local GPU (vLLM) deployment of MinerU2.5 VLM models |
| [strix-halo/deployment.md](strix-halo/deployment.md) | AMD Strix Halo / ROCm deployment reference |

## Notes

- `docker-compose.yml` at the repository root is the default remote-VLM template.
- `Dockerfile` builds the full image with local VLM extras.
- `Dockerfile.slim` builds the slim image for pipeline and http-client backends.
- Runtime secrets should be injected from host environment, CI secrets, Docker secrets, or an explicit external env file. Image builds do not read `.env`.

---

# 部署文档

部署文档说明镜像发布、Docker 变体和特定平台部署方案。根目录 [README.md](../../README.md) 仍是当前快速启动的事实来源。

## 维护中文档

| 文档 | 用途 |
| --- | --- |
| [github-packages.md](github-packages.md) | GitHub Container Registry 发布与清理策略 |
| [local-gpu-vlm-pitfalls.md](local-gpu-vlm-pitfalls.md) | 本地 GPU（vLLM）部署 MinerU2.5 VLM 模型已知坑与修复 |
| [strix-halo/deployment.md](strix-halo/deployment.md) | AMD Strix Halo / ROCm 部署参考 |

## 说明

- 仓库根目录 `docker-compose.yml` 是默认 remote VLM 模板。
- `Dockerfile` 构建包含本地 VLM extras 的完整镜像。
- `Dockerfile.slim` 构建面向 pipeline 和 http-client 后端的精简镜像。
- 运行时敏感配置应从宿主机环境变量、CI secrets、Docker secrets 或显式外部 env file 注入。镜像构建不读取 `.env`。
