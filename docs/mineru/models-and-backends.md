# MinerU 模型与 Backend 指南

## 1. Backend 类型

MinerU 提供多种 Backend，适应不同场景：

| Backend | 说明 | GPU 要求 | 适用场景 |
|---------|------|---------|---------|
| `pipeline` | 传统流水线，无 VLM | 不需要 | 多语言文档，速度快 |
| `vlm-auto-engine` | 本地 VLM，自动选择引擎 | 需要 GPU | 中文/英文文档，高精度 |
| `vlm-http-client` | 远程 VLM API | 不需要 | 中文/英文文档，使用云端 |
| `vlm-vllm-engine` | 本地 VLM，使用 vLLM | 需要 NVIDIA GPU | 中文/英文文档 |
| `vlm-lmdeploy-engine` | 本地 VLM，使用 LMDeploy | 需要 NVIDIA GPU | 中文/英文文档 |
| `vlm-vllm-async-engine` | 本地 VLM，vLLM 异步 | 需要 NVIDIA GPU | 高并发场景 |
| `hybrid-auto-engine` | 本地 OCR + 本地 VLM | 需要 GPU | 多语言 + 高精度 |
| `hybrid-http-client` | 本地 OCR + 远程 VLM | 不需要 GPU | 多语言 + 高精度，推荐 |

**推荐**：`hybrid-http-client` - 本地 OCR + 远程 VLM API，无需 GPU，支持多语言。

---

## 2. 推理引擎自动选择

### 2.1 自动选择逻辑

MinerU 根据操作系统和已安装的包自动选择推理引擎：

| 操作系统 | 优先级 |
|---------|--------|
| **Linux** | vLLM → LMDeploy → transformers |
| **Windows** | LMDeploy → transformers |
| **macOS** | MLX (如果版本支持) → transformers |

### 2.2 手动指定引擎

通过 Backend 参数指定：

```bash
# 使用 vLLM
--backend vlm-vllm-engine

# 使用 LMDeploy
--backend vlm-lmdeploy-engine

# 自动选择
--backend vlm-auto-engine
```

### 2.3 VLM Server 启动

MinerU 提供独立的 VLM Server 命令：

```bash
# 自动选择引擎
mineru-vlm-server

# 手动指定 vLLM
mineru-vlm-server -e vllm

# 手动指定 LMDeploy
mineru-vlm-server -e lmdeploy

# 自定义参数
mineru-vlm-server -e vllm --port 30000 --gpu-memory-utilization 0.5
```

---

## 3. 模型下载

### 3.1 下载命令

```bash
# 下载 pipeline 模型（OCR、Layout、Formula、Table 等）
mineru-models-download -s modelscope -m pipeline

# 下载 VLM 模型（本地推理用）
mineru-models-download -s modelscope -m vlm

# 下载全部模型
mineru-models-download -s modelscope -m all
```

**参数说明**：
- `-s/--source`: `huggingface` 或 `modelscope`（国内推荐 modelscope）
- `-m/--model_type`: `pipeline`、`vlm` 或 `all`

### 3.2 模型存储位置

| 环境变量 | 默认路径 | 说明 |
|---------|---------|------|
| `HF_HOME` | `~/.cache/huggingface` | HuggingFace 模型 |
| `MODELSCOPE_CACHE` | `~/.cache/modelscope` | ModelScope 模型 |

### 3.3 模型列表

**Pipeline 模型**：

| 模型 | 路径 | 用途 |
|------|------|------|
| PP-DocLayoutV2 | `models/Layout/PP-DocLayoutV2` | 文档布局分析 |
| Unimernet Small | `models/MFR/unimernet_hf_small_2503` | 公式识别 |
| PP-FormulaNet Plus M | `models/MFR/pp_formulanet_plus_m` | 公式识别 |
| PaddleOCR Torch | `models/OCR/paddleocr_torch` | OCR 文字识别 |
| Slanet Plus | `models/TabRec/SlanetPlus/slanet-plus.onnx` | 表格结构识别 |
| Unet Structure | `models/TabRec/UnetStructure/unet.onnx` | 表格结构识别 |
| Table Classification | `models/TabCls/paddle_table_cls` | 表格分类 |
| Orientation Classification | `models/OriCls/paddle_orientation_classification` | 方向分类 |

**VLM 模型**：

| 模型 | HuggingFace | ModelScope |
|------|------------|------------|
| MinerU2.5-Pro | `opendatalab/MinerU2.5-Pro-2604-1.2B` | `OpenDataLab/MinerU2.5-Pro-2604-1.2B` |

### 3.4 Docker 持久化

在 `docker-compose.yml` 中配置模型缓存持久化：

```yaml
volumes:
  - ./models:/root/.cache  # 模型缓存持久化
```

环境变量：

```dockerfile
ENV HF_HOME=/root/.cache/huggingface \
    MODELSCOPE_CACHE=/root/.cache/modelscope
```

---

## 4. GPU 兼容性

### 4.1 NVIDIA CUDA

| 引擎 | 支持 | 说明 |
|------|------|------|
| vLLM | ✅ 完全支持 | 推荐用于 NVIDIA GPU |
| LMDeploy | ✅ 完全支持 | 性能优秀 |

**环境变量**：

```bash
# vLLM 设备类型（可选）
export MINERU_VLLM_DEVICE=cuda

# LMDeploy 设备和后端
export MINERU_LMDEPLOY_DEVICE=cuda
export MINERU_LMDEPLOY_BACKEND=pytorch  # 或 turbomind
```

### 4.2 AMD ROCm

| 引擎 | 支持 | 说明 |
|------|------|------|
| vLLM | ⚠️ 需手动优化 | 性能问题，需修改 Triton 算子 |
| LMDeploy | ❌ 不支持 | 只支持 cuda/ascend/maca/camb |

**ROCm 使用建议**：

1. **不推荐本地 VLM**：需要手动修改 vLLM 源码，性能优化复杂
2. **推荐远程 VLM**：使用 `hybrid-http-client` + OpenAI API

**如果必须使用 ROCm + vLLM**，参考官方文档：
- `docs/zh/usage/acceleration_cards/AMD.md`
- 需修改 vLLM 的 `qwen2_vl.py` 添加 Triton 算子

### 4.3 其他加速卡

| 加速卡 | 引擎支持 | 文档 |
|--------|---------|------|
| **华为昇腾 (Ascend)** | LMDeploy (pytorch) | `docs/zh/usage/acceleration_cards/Ascend.md` |
| **海光 DCU** | vLLM | `docs/zh/usage/acceleration_cards/Hygon.md` |
| **摩尔线程 MUSA** | vLLM | `docs/zh/usage/acceleration_cards/MooreThreads.md` |
| **寒武纪 MLU** | vLLM/LMDeploy | `docs/zh/usage/acceleration_cards/Cambricon.md` |
| **昆仑 XPU** | vLLM | `docs/zh/usage/acceleration_cards/Kunlun.md` |
| **天数智芯 CoreX** | vLLM | `docs/zh/usage/acceleration_cards/Iluvatar.md` |

---

## 5. vLLM 与 LMDeploy 使用

### 5.1 vLLM

**安装**：

```bash
# NVIDIA CUDA
pip install vllm

# AMD ROCm（需要手动编译）
git clone https://github.com/vllm-project/vllm.git
pip install -r requirements/rocm.txt
python setup.py develop
```

**启动 VLM Server**：

```bash
mineru-vlm-server -e vllm --port 30000
```

**Backend 使用**：

```bash
# 同步引擎
mineru-parse --backend vlm-vllm-engine input.pdf

# 异步引擎（高并发）
mineru-parse --backend vlm-vllm-async-engine input.pdf
```

**环境变量**：

```bash
export MINERU_VLLM_DEVICE=cuda           # 设备类型
export VLLM_USE_V1=1                     # 使用 v1 引擎
export PYTORCH_ROCM_ARCH=gfx1100         # ROCm 架构（AMD）
```

### 5.2 LMDeploy

**安装**：

```bash
pip install lmdeploy
```

**启动 VLM Server**：

```bash
mineru-vlm-server -e lmdeploy --server-port 30000
```

**Backend 使用**：

```bash
mineru-parse --backend vlm-lmdeploy-engine input.pdf
```

**环境变量**：

```bash
export MINERU_LMDEPLOY_DEVICE=cuda       # cuda/ascend/maca/camb
export MINERU_LMDEPLOY_BACKEND=pytorch   # pytorch/turbomind
```

**LMDeploy Backend 选择**：

| 设备 | 推荐 Backend |
|------|-------------|
| CUDA (compute >= 8.0) | pytorch |
| CUDA (compute < 8.0) | turbomind |
| Ascend/MACA/CAMB | pytorch |

---

## 6. 推荐配置

### 6.1 无 GPU 环境

使用 `hybrid-http-client` + 远程 VLM API：

```bash
# 环境变量
export MINERU_DEFAULT_BACKEND=hybrid-http-client
export MINERU_VLM_BASE_URL=https://api.openai.com/v1
export MINERU_VLM_API_KEY=sk-xxx
export MINERU_VLM_MODEL=gpt-4o

# 只下载 pipeline 模型
mineru-models-download -s modelscope -m pipeline
```

### 6.2 NVIDIA GPU 环境

使用 `vlm-auto-engine` 或 `hybrid-auto-engine`：

```bash
# 环境变量
export MINERU_DEFAULT_BACKEND=vlm-auto-engine

# 下载全部模型
mineru-models-download -s modelscope -m all
```

### 6.3 AMD ROCm 环境

**不推荐本地 VLM**，使用远程 VLM：

```bash
# 环境变量
export MINERU_DEFAULT_BACKEND=hybrid-http-client
export MINERU_VLM_BASE_URL=https://api.openai.com/v1
export MINERU_VLM_API_KEY=sk-xxx
export MINERU_VLM_MODEL=gpt-4o

# 只下载 pipeline 模型
mineru-models-download -s modelscope -m pipeline
```

---

## 7. 常见问题

### Q1: 模型下载很慢？

使用 ModelScope 源：

```bash
mineru-models-download -s modelscope -m pipeline
```

### Q2: 如何查看已下载模型？

```bash
ls ~/.cache/modelscope/hub/
ls ~/.cache/huggingface/hub/
```

### Q3: 如何清理模型缓存？

```bash
rm -rf ~/.cache/modelscope/hub/OpenDataLab
rm -rf ~/.cache/huggingface/hub/opendatalab
```

### Q4: ROCm 性能差怎么办？

参考 `docs/zh/usage/acceleration_cards/AMD.md` 修改 vLLM 源码，或使用远程 VLM API。

### Q5: 如何手动指定推理引擎？

```bash
# 方法 1: 通过 backend 参数
mineru-parse --backend vlm-vllm-engine input.pdf

# 方法 2: 通过环境变量
export MINERU_VLLM_DEVICE=cuda

# 方法 3: 启动独立的 VLM Server
mineru-vlm-server -e vllm
```

---

✌Bazinga！