# Backend and Engine Data Flow

This note separates MinerU Server backend choices from upstream MinerU inference engines.

## Two Layers

| Layer | Meaning | Examples |
| --- | --- | --- |
| Backend | Product/runtime entry selected by API or config | `pipeline`, `hybrid-http-client`, `vlm-auto-engine` |
| Engine | Local VLM execution engine chosen inside upstream MinerU | `vllm`, `lmdeploy`, `transformers`, `mlx` |

The distinction matters because `backend` is part of this service's public task configuration, while `engine` is an upstream implementation detail unless a local VLM backend is used.

## Current Project Paths

### `pipeline`

No VLM is used.

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> structured intermediate data
  -> markdown/json deliverables
```

Use this when no external VLM is configured.

### `vlm-http-client`

The VLM call is remote.

```text
PDF
  -> page/image preparation
  -> OpenAI-compatible VLM HTTP request
  -> model response
  -> markdown/json deliverables
```

The `mineru-mcp` process does not need a local GPU for the VLM part.

### `hybrid-http-client`

Local traditional parsing is combined with remote VLM calls.

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> selected VLM-needed regions/pages
  -> OpenAI-compatible VLM HTTP request
  -> merge local and VLM results
  -> markdown/json deliverables
```

This is the recommended remote-VLM deployment mode.

### `vlm-auto-engine`

The VLM runs locally and upstream MinerU chooses the local engine.

```text
PDF
  -> local VLM path
  -> upstream engine auto-selection
  -> local inference
  -> markdown/json deliverables
```

The chosen engine can vary with OS and installed packages.

### `hybrid-auto-engine`

Local OCR/layout parsing is combined with local VLM inference.

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> local VLM path
  -> upstream engine auto-selection
  -> merge results
  -> markdown/json deliverables
```

Use this only when the local GPU/runtime has been validated.

## Why `auto-engine` Can Surprise You

`*-auto-engine` does not guarantee vLLM. It means upstream MinerU will try to select an engine. If vLLM or LMDeploy is unavailable, the path may fall back to `transformers`, which has different performance and dependency behavior.

## Deployment Guidance

- Default compose route: `hybrid-http-client` + sibling `vlm-server`.
- No external VLM: `pipeline`.
- Local GPU experiments: full image + low concurrency + explicit validation.
- If debugging engine selection, inspect the actual task backend and process logs before assuming vLLM is active.

---

# Backend 与推理引擎数据链路

本文区分 MinerU Server 的 backend 选择和上游 MinerU 的推理 engine。

## 两层概念

| 层 | 含义 | 示例 |
| --- | --- | --- |
| Backend | 由 API 或配置选择的产品/运行入口 | `pipeline`, `hybrid-http-client`, `vlm-auto-engine` |
| Engine | 上游 MinerU 内部选择的本地 VLM 执行引擎 | `vllm`, `lmdeploy`, `transformers`, `mlx` |

这一区分很重要：`backend` 是本服务任务配置的一部分，而 `engine` 通常是上游实现细节；只有使用本地 VLM backend 时才需要重点关注。

## 当前项目路径

### `pipeline`

不使用 VLM。

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> structured intermediate data
  -> markdown/json deliverables
```

没有配置外部 VLM 时使用该模式。

### `vlm-http-client`

VLM 调用走远程服务。

```text
PDF
  -> page/image preparation
  -> OpenAI-compatible VLM HTTP request
  -> model response
  -> markdown/json deliverables
```

`mineru-mcp` 进程的 VLM 部分不需要本地 GPU。

### `hybrid-http-client`

本地传统解析与远程 VLM 调用结合。

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> selected VLM-needed regions/pages
  -> OpenAI-compatible VLM HTTP request
  -> merge local and VLM results
  -> markdown/json deliverables
```

这是当前推荐的 remote VLM 部署模式。

### `vlm-auto-engine`

VLM 在本地运行，由上游 MinerU 自动选择本地 engine。

```text
PDF
  -> local VLM path
  -> upstream engine auto-selection
  -> local inference
  -> markdown/json deliverables
```

实际选择的 engine 会随操作系统和安装包变化。

### `hybrid-auto-engine`

本地 OCR/layout 解析与本地 VLM 推理结合。

```text
PDF
  -> local OCR/layout/formula/table pipeline
  -> local VLM path
  -> upstream engine auto-selection
  -> merge results
  -> markdown/json deliverables
```

仅在本地 GPU/运行时已经验证后使用。

## 为什么 `auto-engine` 可能出乎意料

`*-auto-engine` 不保证一定走 vLLM。它表示上游 MinerU 会尝试选择 engine。如果 vLLM 或 LMDeploy 不可用，路径可能回退到 `transformers`，性能和依赖行为都会不同。

## 部署建议

- 默认 compose 路线：`hybrid-http-client` + 同 compose 内 `vlm-server`。
- 没有外部 VLM：使用 `pipeline`。
- 本地 GPU 实验：使用 full 镜像 + 低并发 + 显式验证。
- 排查 engine 选择时，先看任务实际 backend 和进程日志，不要直接假设已经走 vLLM。
