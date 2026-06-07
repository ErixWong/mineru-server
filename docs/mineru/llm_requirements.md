# MinerU LLM 需求分析文档

## 概述

本文档分析 MinerU 文档解析工具所需的 LLM（大语言模型）和 VLM（视觉语言模型），帮助您理解不同后端的模型需求，以及如何配置外部 API 替代本地模型推理。

---

## 1. 文档处理流程总览

MinerU 解析一份 PDF 文档，需要经过以下处理流程：

| 阶段               | 工序     | 功能                           | 是否需要模型    | Pipeline 后端                      | VLM 后端       | Hybrid 后端         |
| ------------------ | -------- | ------------------------------ | --------------- | ---------------------------------- | -------------- | ------------------- |
| **输入**     | —       | PDF/图片文档输入               | —              | —                                 | —             | —                  |
| **预处理**   | PDF 渲染 | 将 PDF 页面转换为图像          | ❌不需要        | pypdfium2工具库                    | pypdfium2      | pypdfium2           |
| **分析识别** | 版面分析 | 检测标题、段落、表格、图片位置 | ✅ 需要         | PP-DocLayoutV2 (本地)              | VLM (本地/API) | VLM (本地/API)      |
| **分析识别** | 内容识别 | 识别文字、公式、表格内容       | ✅ 需要         | PaddleOCR + UniMERNet + SlanetPlus | VLM 直接输出   | VLM + 本地模型协作  |
| **后处理**   | 结构优化 | 方向校正、标题层级优化         | ✅ 需要（可选） | OriCls + LLM (可选)                | LLM (可选)     | OriCls + LLM (可选) |
| **输出**     | —       | Markdown / JSON / HTML         | —              | —                                 | —             | —                  |

### 1.1 关键理解

- **PDF 渲染**：使用 pypdfium2 工具库（非模型），所有后端都需要，无差异
- **版面分析**：需要模型，VLM/Hybrid 后端可通过外部 API 完成
- **内容识别**：需要模型，Pipeline/Hybrid 后端需要本地模型，VLM 后端完全依赖 VLM
- **结构优化**：需要模型（可选功能），所有后端均可通过外部 API 完成

---

## 2. 后端架构与模型需求

### 2.1 后端分类与核心概念

MinerU 使用两种模式处理文档：传统模型架构的 **Pipeline 后端** 和视觉语言模型架构的 **VLM 后端**。这两种模式可以本地运行或通过外部 API 调用，还可以组合成第三种模式：**Hybrid 混合架构**。

| 特性               | Pipeline 后端                            | VLM 后端                                                         | Hybrid 后端                                      |
| ------------------ | ---------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------ |
| **架构类型** | 传统模型架构                             | 视觉语言模型架构                                                 | 混合架构                                         |
| **使用模型** | Layout、OCR、MFR、TabRec、OriCls         | VLM（MinerU2.5-1.2B）                                            | VLM + 传统模型                                   |
| **推理引擎** | PyTorch / ONNX                           | vLLM / LMDeploy / Transformers（本地）或 OpenAI 兼容 API（远程） | VLM 引擎 + PyTorch/ONNX                          |
| **推理方式** | 仅本地运行                               | 本地（auto-engine）或远程 API（http-client）                     | VLM 可远程，传统模型必须本地                     |
| **需要 GPU** | 可选（CPU 也可运行）                     | 本地推理必须，远程 API 不需要                                    | 本地推理必须，远程 API 可选                      |
| **支持语言** | 多语言                                   | 仅中英文                                                         | 多语言                                           |
| **精度**     | 中等                                     | 高                                                               | 最高                                             |
| **可用后端** | `pipeline`                             | `vlm-auto-engine`、`vlm-http-client`                         | `hybrid-auto-engine`、`hybrid-http-client`   |
| **特点**     | • 无幻觉 ``• 稳定可靠``• 无需外部依赖 | • 版面理解强 ``• 表格/公式识别精度高``• 工序简化              | • 结合两者优势 ``• 精度最高``• 速度与精度平衡 |

**核心理解**：VLM 是"全能模型"，可替代所有 Pipeline 模型；Pipeline 模型是"专用模型"，只负责单一任务。

### 2.2 后端与模型需求对照

| 后端                   | VLM 来源             | Pipeline 模型来源   | 需要下载模型       | 需要本地 GPU     | 支持语言 | 精度 |
| ---------------------- | -------------------- | ------------------- | ------------------ | ---------------- | -------- | ---- |
| `pipeline`           | ❌ 不使用            | ✅ 本地运行（全部） | 约 500MB           | 可选（CPU 也可） | 多语言   | 中等 |
| `vlm-auto-engine`    | ✅ 本地推理          | ❌ 不使用           | 约 2.5GB           | **必须**   | 中英文   | 高   |
| `vlm-http-client`    | ✅**远程 API** | ❌ 不使用           | **无需下载** | 不需要           | 中英文   | 高   |
| `hybrid-auto-engine` | ✅ 本地推理          | ✅ 本地运行（全部） | 约 3GB             | **必须**   | 多语言   | 最高 |
| `hybrid-http-client` | ✅**远程 API** | ✅ 本地运行（全部） | 约 500MB           | 可选             | 多语言   | 最高 |

**说明**：

- **VLM 来源**：`*-http-client` 后端使用远程 API，`*-auto-engine` 后端使用本地推理
- **Pipeline 模型**：Layout、OCR、MFR、TabRec、TabCls、OriCls 等传统模型，仅支持本地运行
- **标题优化 LLM**：可选功能，所有后端均可配置外部 API 使用

### 2.3 后端选择建议

| 环境条件                 | 推荐后端                     | 说明                                     |
| ------------------------ | ---------------------------- | ---------------------------------------- |
| **无 GPU**         | `vlm-http-client`          | 纯远程 VLM，无需下载任何模型             |
| **无 GPU**         | `hybrid-http-client`       | 远程 VLM + 本地 Pipeline，需下载约 500MB |
| **有 GPU (16GB+)** | `hybrid-auto-engine`       | 本地 VLM + 本地 Pipeline，精度最高       |
| **有 GPU (4-8GB)** | `hybrid-auto-engine`       | 使用 1.2B 小模型，显存占用低             |
| **多语言文档**     | `pipeline` 或 `hybrid-*` | VLM 仅支持中英文                         |
| **中英文文档**     | `vlm-*` 或 `hybrid-*`    | VLM 对中英文效果最佳                     |

---

## 3. 本地 OCR 与 VLM 的关系

### 3.1 本地 OCR 的组成

**本地 OCR** 是指 MinerU 在本地运行的光学字符识别模型，基于 **PaddleOCR** 的 PyTorch 实现：

| 组件               | 功能                   | 模型文件位置                                         |
| ------------------ | ---------------------- | ---------------------------------------------------- |
| **文本检测** | 检测图像中的文字区域   | `models/OCR/paddleocr_torch/ch_PP-OCRv4_det_infer` |
| **文本识别** | 识别检测到的文字内容   | `models/OCR/paddleocr_torch/ch_PP-OCRv4_rec_infer` |
| **方向分类** | 检测文字方向并旋转校正 | `models/OriCls/paddle_orientation_classification`  |

### 3.2 本地 OCR 与各后端的关系

| 后端                   | 本地 OCR 角色          | VLM 角色                     |
| ---------------------- | ---------------------- | ---------------------------- |
| `pipeline`           | **主要识别方式** | 不使用                       |
| `vlm-http-client`    | 不使用                 | **主要识别方式**       |
| `vlm-auto-engine`    | 不使用                 | **主要识别方式**       |
| `hybrid-http-client` | 识别行内公式和补充文本 | 版面分析、表格识别、图片理解 |
| `hybrid-auto-engine` | 识别行内公式和补充文本 | 版面分析、表格识别、图片理解 |

### 3.3 为什么 Pipeline 模型不支持外部 API？

**技术原因**：

- Pipeline 模型是**传统深度学习模型**（基于 PyTorch/ONNX），不是大语言模型
- 它们需要精细的输入预处理和输出后处理，这些逻辑硬编码在 MinerU 内部
- 没有统一的 API 标准（如 OpenAI 兼容格式）

**替代方案**：

| 想用外部 API 替代的功能              | 解决方案                                             |
| ------------------------------------ | ---------------------------------------------------- |
| 版面分析 / OCR / 公式识别 / 表格识别 | 使用 `vlm-http-client`，VLM API 完成全部           |
| **全部功能**                   | 使用 `vlm-http-client`，**无需任何本地模型** |

---

## 4. 模型清单

### 4.1 VLM 模型（仅 VLM/Hybrid 后端）

| 模型                | HuggingFace 仓库                    | ModelScope 仓库                     | 模型大小 |
| ------------------- | ----------------------------------- | ----------------------------------- | -------- |
| MinerU2.5-2509-1.2B | `opendatalab/MinerU2.5-2509-1.2B` | `OpenDataLab/MinerU2.5-2509-1.2B` | ~2.5GB   |

### 4.2 Pipeline 模型（仅 Pipeline/Hybrid 后端）

所有 Pipeline 模型位于统一仓库：

- HuggingFace: `opendatalab/PDF-Extract-Kit-1.0`
- ModelScope: `OpenDataLab/PDF-Extract-Kit-1.0`

| 模型路径                                            | 功能               | 文件大小 |
| --------------------------------------------------- | ------------------ | -------- |
| `models/Layout/PP-DocLayoutV2`                    | 版面检测           | ~150MB   |
| `models/OCR/paddleocr_torch`                      | 文本检测+识别      | ~100MB   |
| `models/MFR/unimernet_hf_small_2503`              | 公式识别（小模型） | ~200MB   |
| `models/MFR/pp_formulanet_plus_m`                 | 公式识别（增强版） | ~150MB   |
| `models/TabRec/SlanetPlus/slanet-plus.onnx`       | 表格结构识别       | ~50MB    |
| `models/TabRec/UnetStructure/unet.onnx`           | 无线表格识别       | ~30MB    |
| `models/TabCls/paddle_table_cls`                  | 表格分类           | ~10MB    |
| `models/OriCls/paddle_orientation_classification` | 方向分类           | ~5MB     |

**总下载量**：约 500MB（Pipeline 模型） + 2.5GB（VLM 模型，如需要）

### 4.3 硬件支持情况

| 硬件类型                      | VLM 模型              | Pipeline 模型 | 说明                            |
| ----------------------------- | --------------------- | ------------- | ------------------------------- |
| **NVIDIA GPU (CUDA)**   | ✅ 原生支持           | ✅ 原生支持   | 推荐，性能最佳                  |
| **Apple Silicon (MPS)** | ✅ 支持（mlx-engine） | ✅ 支持       | Mac M1/M2/M3 可用               |
| **华为昇腾 (NPU)**      | ✅ 支持（需适配）     | ✅ 支持       | 需安装 torch_npu                |
| **摩尔线程 (MUSA)**     | ✅ 支持（需适配）     | ✅ 支持       | 需安装 torch-musa               |
| **寒武纪 (MLU)**        | ✅ 支持（需适配）     | ✅ 支持       | 需安装 torch-mlu                |
| **海光 (MACA)**         | ✅ 支持（LMDeploy）   | ✅ 支持       | 通过 LMDeploy                   |
| **AMD GPU (ROCm)**      | ✅ 需优化             | ✅ 原生支持   | VLM 需 Triton 补丁              |
| **CPU**                 | ❌ 不推荐             | ✅ 支持       | VLM 推理太慢，Pipeline 可用 CPU |

---

## 5. VLM API 配置方法

使用 `*-http-client` 后端时，需要配置 VLM API 连接。

### 5.1 环境变量（推荐，无需配置文件）

设置环境变量后，`vlm_analyze.py` 会直接读取，**无需配置 `mineru.json` 文件**。

```bash
# VLM 配置（用于文档解析）
export MINERU_VLM_API_KEY="sk-your-api-key"
export MINERU_VLM_BASE_URL="https://api.openai.com/v1"
export MINERU_VLM_MODEL="gpt-4o"

# 标题优化 LLM（可选）
export MINERU_TITLE_API_KEY="sk-your-api-key"
export MINERU_TITLE_BASE_URL="https://api.openai.com/v1"
export MINERU_TITLE_MODEL="gpt-4o-mini"
```

**Windows (PowerShell)**：

```powershell
# 临时设置（当前会话）
$env:MINERU_VLM_API_KEY="sk-your-api-key"
$env:MINERU_VLM_BASE_URL="https://api.openai.com/v1"
$env:MINERU_VLM_MODEL="gpt-4o"

# 永久设置（用户环境变量）
[Environment]::SetEnvironmentVariable("MINERU_VLM_API_KEY", "sk-your-api-key", "User")
[Environment]::SetEnvironmentVariable("MINERU_VLM_BASE_URL", "https://api.openai.com/v1", "User")
[Environment]::SetEnvironmentVariable("MINERU_VLM_MODEL", "gpt-4o", "User")
```

**使用 .env 文件**：

MCP Server 启动时会自动加载 `.env` 文件：

```bash
# .env 文件内容
MINERU_VLM_API_KEY=sk-your-api-key
MINERU_VLM_BASE_URL=https://api.openai.com/v1
MINERU_VLM_MODEL=gpt-4o
```

### 5.2 配置文件

编辑 `~/.mineru/mineru.json`：

```json
{
    "models-dir": {
        "pipeline": "",
        "vlm": ""
    },
    "llm-aided-config": {
        "vlm": {
            "api_key": "sk-your-api-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o"
        },
        "title_aided": {
            "enable": true,
            "api_key": "sk-your-api-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "enable_thinking": false
        }
    },
    "config_version": "1.3.1"
}
```

### 5.3 命令行参数

```bash
mineru -p document.pdf -o output/ \
    -b vlm-http-client \
    -u https://api.openai.com/v1 \
    --api-key sk-your-api-key \
    --model gpt-4o
```

---

## 6. VLM 模型选择指南

### 6.1 推荐模型

| 使用场景                   | 推荐模型                | 提供商    | 说明                                 |
| -------------------------- | ----------------------- | --------- | ------------------------------------ |
| **最佳精度**         | GPT-4o                  | OpenAI    | 目前最强的文档理解能力               |
| **最佳精度（备选）** | Claude 3.5 Sonnet       | Anthropic | 与 GPT-4o 相当，某些场景表格识别更好 |
| **中文文档首选**     | Qwen2.5-VL-72B-Instruct | 阿里云    | 中文理解优秀                         |
| **性价比首选**       | GPT-4o-mini             | OpenAI    | 速度快，价格低                       |
| **性价比（中文）**   | Qwen2.5-VL-7B-Instruct  | 阿里云    | 中文场景性价比高，可自托管           |
| **自托管推荐**       | Qwen2.5-VL-7B-Instruct  | 本地/vLLM | 7B 参数，单卡 16GB 显存可运行        |
| **多语言文档**       | Gemini 1.5 Pro          | Google    | 多语言支持优秀                       |

### 6.2 选择建议

- **预算充足 + 高精度要求** → GPT-4o 或 Claude 3.5 Sonnet
- **中文文档为主** → Qwen2.5-VL 系列
- **成本敏感** → GPT-4o-mini 或 Qwen2.5-VL-7B
- **数据隐私要求高** → 自托管 Qwen2.5-VL-7B

### 6.3 资源需求

| 组件                                     | GPU               | 内存  | 存储           |
| ---------------------------------------- | ----------------- | ----- | -------------- |
| **本地 VLM (`vlm-auto-engine`)** | NVIDIA 16GB+ 显存 | 32GB+ | 模型权重 20GB+ |
| **HTTP-Client 后端**               | 不需要            | 8GB+  | 无             |
| **本地 OCR**                       | 可选，2-4GB 显存  | 2-4GB | 约 500MB       |

---

## 7. 核心概念解释

### 7.1 文档解析 VLM（视觉语言模型）

**是什么**：**多模态模型**，既能处理图像也能处理文本

**作用**：

- 输入：文档页面图像（PDF 页面截图）
- 输出：文档结构（标题、段落、表格位置等）+ 文字内容

**为什么是多模态**：

- 需要"看"到文档图像（视觉能力）
- 需要"理解"并输出文字（语言能力）

**使用场景**：

- `vlm-http-client` 后端：完全依赖 VLM 解析文档
- `hybrid-http-client` 后端：VLM 负责版面分析，本地 OCR 辅助文字识别

### 7.2 标题优化文本模型

**是什么**：**纯文本模型**，只处理文字，不处理图像

**作用**：

- 输入：文档中的标题文字列表
- 输出：标题的层级结构（一级标题、二级标题等）

**使用场景**：

- 在 `mineru.json` 中配置 `llm-aided-config.title_aided`
- 可选功能，用于优化文档的标题层级结构

### 7.3 Hybrid 后端（混合后端）

**是什么**：结合两种技术的文档解析方式

| 组件                       | 负责什么                                 | 模型类型                   |
| -------------------------- | ---------------------------------------- | -------------------------- |
| **VLM（远程）**      | 版面分析（找标题、段落、表格、图片位置） | 多模态模型                 |
| **本地 OCR（本地）** | 精确文字识别（识别具体文字内容）         | 传统 OCR 模型（PaddleOCR） |

**为什么叫"混合"**：

- 混合了"远程 VLM"和"本地 OCR"两种技术
- VLM 擅长理解文档结构
- 本地 OCR 擅长精确识别小字体文字
- 两者结合，速度和精度更平衡

---

## 8. VLM HTTP-Client 后端参数配置详解

### 8.1 背景：官方 Bug 修复

**问题描述**：MinerU 官方代码存在一个已知 Bug（GitHub Issue #3994），当使用 `vlm-http-client` 后端时，`server_headers` 参数从未传递给 `MinerUClient`，导致 API 调用返回 `{"error":"Unauthorized"}` 错误。

**修复方案**：在 [`vlm_analyze.py`](src/mineru/backend/vlm/vlm_analyze.py) 中添加了完整的环境变量和配置文件读取支持。

### 8.2 修改内容

修改文件：`src/mineru/backend/vlm/vlm_analyze.py`

**修改点 1**：添加 `model_name` 参数提取（第 74 行）

```python
model_name = kwargs.get("model_name", None)  # for http-client backend only (VLM model name)
```

**修改点 2**：添加环境变量和配置文件读取逻辑（第 80-119 行）

```python
# For http-client backend, read configuration from multiple sources with priority:
# 1. Environment variables (highest priority, no config file needed)
#    - MINERU_VLM_API_KEY: API key for authentication
#    - MINERU_VLM_MODEL: VLM model name (optional, auto-detect if not set)
# 2. llm-aided-config.vlm from config file (fallback if env vars not set)
# 3. Parameters passed by caller (explicit way, respected if provided)
# Note: With environment variables set, mineru.json config file is NOT required!
if backend == "http-client":
    # Handle API key for server_headers
    if server_url is not None and server_headers is None:
        # First check environment variable (highest priority)
        api_key = os.getenv("MINERU_VLM_API_KEY")
        if api_key:
            server_headers = {"Authorization": f"Bearer {api_key}"}
            logger.info(f"Set server_headers from MINERU_VLM_API_KEY env var")
        else:
            # Then check config file (fallback)
            ...
    
    # Handle model_name (optional, server can auto-detect if only one model)
    if model_name is None:
        # First check environment variable
        model_name = os.getenv("MINERU_VLM_MODEL")
        if model_name:
            logger.info(f"Set model_name from MINERU_VLM_MODEL env var: {model_name}")
        else:
            # Then check config file
            ...
```

**修改点 3**：将 `model_name` 传递给 `MinerUClient`（第 274 行）

```python
predictor = MinerUClient(
    backend=backend,
    ...
    server_url=server_url,
    model_name=model_name,  # VLM model name for http-client backend
    server_headers=server_headers,
    ...
)
```

### 8.3 HTTP-Client 后端参数支持情况

| 参数 | 状态 | 来源 | 说明 |
|------|------|------|------|
| `server_url` | ✓ 支持 | FastAPI 参数 + kwargs | VLM API 服务地址 |
| `model_name` | ✓ **已添加** | `MINERU_VLM_MODEL` 环境变量 + config 文件 | VLM 模型名称 |
| `server_headers` | ✓ **已添加** | 从 `MINERU_VLM_API_KEY` 环境变量构建 + config 文件 | API 认证头 |
| `http_timeout` | ✓ 支持 | kwargs 参数 (默认 600s) | HTTP 请求超时 |
| `max_retries` | ✓ 支持 | kwargs 参数 (默认 3) | 最大重试次数 |
| `retry_backoff_factor` | ✓ 支持 | kwargs 参数 (默认 0.5) | 重试退避因子 |
| `max_concurrency` | ✓ **已添加** | `MINERU_VLM_MAX_CONCURRENCY` 环境变量 (默认 100) | 最大并发数 |
| `batch_size` | ✓ 支持 | kwargs 参数 (默认 0) | 批处理大小 |

### 8.4 统一的环境变量命名

所有 VLM 相关环境变量统一使用 `MINERU_VLM_*` 前缀：

| 环境变量 | 用途 | 对应 MinerUClient 参数 |
|----------|------|------------------------|
| `MINERU_VLM_API_KEY` | VLM API 认证密钥 | 构建 `server_headers` |
| `MINERU_VLM_BASE_URL` | VLM API 服务地址 | `server_url` |
| `MINERU_VLM_MODEL` | VLM 模型名称 | `model_name` |
| `MINERU_VLM_MAX_CONCURRENCY` | 最大并发请求数 | `max_concurrency` |
| `MINERU_VLM_FORMULA_ENABLE` | 公式识别开关 | 内部处理 |
| `MINERU_VLM_TABLE_ENABLE` | 表格识别开关 | 内部处理 |

### 8.5 配置优先级

```
环境变量 > 配置文件 > 显式参数
```

1. **环境变量**（最高优先级，无需配置文件）:
   - `MINERU_VLM_API_KEY` → 构建 `server_headers`
   - `MINERU_VLM_MODEL` → 设置 VLM 模型名

2. **配置文件**（备选方案）:
   - `~/.mineru/mineru.json` 中的 `llm-aided-config.vlm.api_key` 和 `llm-aided-config.vlm.model`

3. **显式参数**（调用方传入）:
   - 通过函数参数直接传入

### 8.6 MCP Server 集成

MCP Server 启动时会自动加载 `.env` 文件到环境变量：

```python
# mcp-server/src/mineru_mcp/cli.py
from dotenv import load_dotenv

env_path = Path.cwd() / ".env"
if env_path.exists():
    load_dotenv(env_path)  # 将 .env 文件内容加载到 os.environ
```

**重要改进**：修改后的 `vlm_analyze.py` **优先读取环境变量**，因此：

- ✅ **只需设置环境变量**，无需配置 `mineru.json`
- ✅ `vlm_analyze.py` 和 `llm_aided.py` 直接从环境变量读取，无需配置同步

### 8.7 .env 文件与环境变量的关系

**概念区别**：

| 类型 | 说明 | 生命周期 | 作用域 |
|------|------|----------|--------|
| `.env` 文件 | 文本配置文件，存储键值对 | 持久化存储 | 项目目录 |
| 环境变量 | 操作系统级变量，通过 `os.getenv()` 读取 | 进程生命周期 | 当前进程及其子进程 |

**转换流程**：

```
.env 文件 → load_dotenv() → 环境变量 (os.environ) → os.getenv() 读取
```

**配置读取路径**：

| 路径 | 流程 | 是否需要 mineru.json |
|------|------|---------------------|
| **唯一路径** | `.env` → `load_dotenv()` → 环境变量 → `vlm_analyze.py` 直接读取 | ❌ **不需要** |

**优先级**：路径 1（环境变量）优先于路径 2（配置文件），确保设置环境变量后配置立即生效，无需额外配置文件。

### 8.8 完整配置示例

**方式一：仅使用环境变量（推荐）**

```bash
# .env 文件
MINERU_VLM_API_KEY=sk-your-api-key
MINERU_VLM_BASE_URL=https://api.openai.com/v1
MINERU_VLM_MODEL=gpt-4o
```

启动 MCP Server 后，`vlm_analyze.py` 直接从环境变量读取，无需 `mineru.json`。

**方式二：使用配置文件（备选）**

如果未设置环境变量，`vlm_analyze.py` 会从 `~/.mineru/mineru.json` 读取：

```json
{
    "llm-aided-config": {
        "vlm": {
            "api_key": "sk-your-api-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o"
        }
    }
}
```

---

## 9. 参考

- MinerU GitHub：https://github.com/opendatalab/MinerU
- GitHub Issue #3994：https://github.com/opendatalab/MinerU/issues/3994
- vLLM 文档：https://docs.vllm.ai/
- OpenAI API 参考：https://platform.openai.com/docs/api-reference
- Qwen2.5-VL：https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct
- PaddleOCR：https://github.com/PaddlePaddle/PaddleOCR
