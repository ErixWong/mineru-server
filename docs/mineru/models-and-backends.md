# MinerU Models and Backends

This document describes the backend choices that matter to MinerU Server. For public API usage and deployment commands, see the root [README.md](../../README.md).

## Current Project Backends

The service accepts the following backend values:

| Backend | Description | Local GPU needed by `mineru-mcp` | Recommended use |
| --- | --- | --- | --- |
| `hybrid-http-client` | Local OCR/layout pipeline plus remote OpenAI-compatible VLM | No | Default remote-VLM deployment |
| `vlm-http-client` | Remote OpenAI-compatible VLM path | No | Chinese/English documents when VLM is external |
| `pipeline` | Traditional local pipeline without VLM | No | Local debugging or environments without VLM |
| `vlm-auto-engine` | Local VLM path with engine auto-selection | Depends on local runtime | Local GPU experiments |
| `hybrid-auto-engine` | Local OCR/layout plus local VLM | Depends on local runtime | Local GPU experiments with multi-language needs |

The project default is `hybrid-http-client`.

Use `pipeline` when no external VLM service is configured.

## Full vs Slim Image

| Image | Dockerfile | Intended support |
| --- | --- | --- |
| Full | `Dockerfile` | Installs MinerU with `vlm,pipeline,vllm` extras. Suitable for local VLM experiments. |
| Slim | `Dockerfile.slim` | Installs MinerU with `pipeline`. Suitable for `pipeline`, `hybrid-http-client`, and `vlm-http-client`. |

## Remote VLM Configuration

`*-http-client` backends use an OpenAI-compatible VLM service:

```bash
MINERU_VL_SERVER=http://localhost:30000/v1
MINERU_VL_API_KEY=
MINERU_VL_MODEL_NAME=MinerU2.5-Pro-2605-1.2B
MINERU_VLM_MAX_CONCURRENCY=2
```

In the default `docker-compose.yml`, `mineru-mcp` talks to the sibling `vlm-server` service through:

```text
http://vlm-server:30000/v1
```

## Model Storage

Common model/cache paths:

```text
/root/.cache/huggingface
/root/.cache/modelscope
```

The compose template mounts:

```text
./models:/root/.cache
```

This keeps model downloads outside the container layer.

## Engine Notes

MinerU upstream has additional explicit engine backends such as vLLM and LMDeploy variants. MinerU Server intentionally exposes a smaller backend set through `VALID_BACKENDS` in `src/mineru_mcp/config.py`.

When using `*-auto-engine`, upstream MinerU chooses a local engine based on OS and installed packages. This can fall back to `transformers` if vLLM or LMDeploy is unavailable.

## Practical Recommendations

- For server deployment with a separate VLM service, use `hybrid-http-client`.
- For quick local validation without VLM, use `pipeline`.
- For local GPU exploration, use the full image and test `vlm-auto-engine` or `hybrid-auto-engine`.
- Keep `MINERU_MAX_CONCURRENT` low when experimenting with local GPU backends.

---

# MinerU 模型与 Backend 指南

本文说明 MinerU Server 需要关注的 backend 选择。公开 API 用法和部署命令以根目录 [README.md](../../README.md) 为准。

## 当前项目 Backends

服务接受以下 backend 值：

| Backend | 说明 | `mineru-mcp` 本地是否需要 GPU | 推荐场景 |
| --- | --- | --- | --- |
| `hybrid-http-client` | 本地 OCR/layout pipeline + OpenAI 兼容远程 VLM | 不需要 | 默认 remote VLM 部署 |
| `vlm-http-client` | OpenAI 兼容远程 VLM 路径 | 不需要 | VLM 外置的中英文文档 |
| `pipeline` | 无 VLM 的传统本地 pipeline | 不需要 | 本地调试或无 VLM 环境 |
| `vlm-auto-engine` | 本地 VLM 路径，由上游自动选择 engine | 取决于本地运行时 | 本地 GPU 实验 |
| `hybrid-auto-engine` | 本地 OCR/layout + 本地 VLM | 取决于本地运行时 | 多语言 + 本地 GPU 实验 |

项目默认值是 `hybrid-http-client`。

没有配置外部 VLM 服务时，使用 `pipeline`。

## Full 与 Slim 镜像

| 镜像 | Dockerfile | 预期支持 |
| --- | --- | --- |
| Full | `Dockerfile` | 安装 MinerU 的 `vlm,pipeline,vllm` extras，适合本地 VLM 实验。 |
| Slim | `Dockerfile.slim` | 安装 MinerU 的 `pipeline` extras，适合 `pipeline`、`hybrid-http-client`、`vlm-http-client`。 |

## Remote VLM 配置

`*-http-client` 后端使用 OpenAI 兼容 VLM 服务：

```bash
MINERU_VL_SERVER=http://localhost:30000/v1
MINERU_VL_API_KEY=
MINERU_VL_MODEL_NAME=MinerU2.5-Pro-2605-1.2B
MINERU_VLM_MAX_CONCURRENCY=2
```

默认 `docker-compose.yml` 中，`mineru-mcp` 通过以下地址访问同 compose 内的 `vlm-server`：

```text
http://vlm-server:30000/v1
```

## 模型存储

常见模型/缓存路径：

```text
/root/.cache/huggingface
/root/.cache/modelscope
```

Compose 模板挂载：

```text
./models:/root/.cache
```

这样模型下载不会写入容器层。

## Engine 说明

上游 MinerU 还有 vLLM、LMDeploy 等显式 engine backend。MinerU Server 通过 `src/mineru_mcp/config.py` 中的 `VALID_BACKENDS` 有意暴露较小的 backend 集合。

使用 `*-auto-engine` 时，上游 MinerU 会根据操作系统和已安装包选择本地 engine。如果 vLLM 或 LMDeploy 不可用，可能回退到 `transformers`。

## 实用建议

- 独立 VLM 服务部署：使用 `hybrid-http-client`。
- 无 VLM 的本地快速验证：使用 `pipeline`。
- 本地 GPU 实验：使用 full 镜像并测试 `vlm-auto-engine` 或 `hybrid-auto-engine`。
- 本地 GPU backend 实验时，把 `MINERU_MAX_CONCURRENT` 设低。
