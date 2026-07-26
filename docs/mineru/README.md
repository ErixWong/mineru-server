# MinerU Notes

This directory explains how this project uses upstream MinerU backends, models, configuration, and inference engines. These docs are technical references; the root [README.md](../../README.md) is still the current product contract.

## Documents

| Document | Status |
| --- | --- |
| [models-and-backends.md](models-and-backends.md) | Maintained backend/model guide |
| [backend-and-engine-dataflow.md](backend-and-engine-dataflow.md) | Maintained backend and engine data-flow guide |
| [llm_requirements.md](llm_requirements.md) | Research/reference note; verify against current code before treating as contract |
| [config_flow.md](config_flow.md) | Deep upstream configuration research; reference only |
| [container_usage.md](container_usage.md) | Historical upstream MinerU container usage note; reference only |

## Current Project Backend Set

- `pipeline`
- `vlm-http-client`
- `hybrid-http-client`
- `vlm-auto-engine`
- `hybrid-auto-engine`

The current recommended default for remote-VLM deployments is `hybrid-http-client`. Use `pipeline` when no external VLM service is configured.

---

# MinerU 说明

本目录说明当前项目如何使用上游 MinerU 的 backend、模型、配置和推理引擎。这些文档是技术参考；根目录 [README.md](../../README.md) 仍是当前产品契约。

## 文档清单

| 文档 | 状态 |
| --- | --- |
| [models-and-backends.md](models-and-backends.md) | 维护型 backend/模型指南 |
| [backend-and-engine-dataflow.md](backend-and-engine-dataflow.md) | 维护型 backend 与 engine 数据链路说明 |
| [llm_requirements.md](llm_requirements.md) | 研究/参考笔记；作为契约使用前需对照当前代码 |
| [config_flow.md](config_flow.md) | 上游配置链路深度研究；仅作参考 |
| [container_usage.md](container_usage.md) | 上游 MinerU 容器使用历史笔记；仅作参考 |

## 当前项目 backend 集合

- `pipeline`
- `vlm-http-client`
- `hybrid-http-client`
- `vlm-auto-engine`
- `hybrid-auto-engine`

remote VLM 部署当前推荐默认使用 `hybrid-http-client`。未配置外部 VLM 服务时，真实 PDF 调试建议使用 `pipeline`。
