# MinerU 混合模式部署指南 - Strix Halo (ROCm)

> Status: Platform-specific deployment reference. This guide is useful for AMD Strix Halo / ROCm experiments, but the root README and root `docker-compose.yml` remain the current general deployment contract.
>
> 状态：特定平台部署参考。本文适用于 AMD Strix Halo / ROCm 实验；通用部署契约仍以根 README 和根目录 `docker-compose.yml` 为准。

## 概述

本指南介绍如何在 **AMD Strix Halo** 平台上使用 **ROCm** 运行 MinerU，提供**两组部署方案**：

| 方案 | 名称 | VLM 运行位置 | 需要 vLLM | 复杂度 | 推荐度 |
|------|------|-------------|----------|--------|--------|
| **方案 A** | 纯第三方 API | 远程 (OpenAI/阿里云等) | ❌ 不需要 | ⭐ 简单 | ⭐⭐⭐⭐⭐ |
| **方案 B** | 本地 ROCm 推理 | 本地 (ROCm + vLLM) | ✅ 需要 | ⭐⭐⭐⭐ 复杂 | ⭐⭐⭐ |

### 方案对比

| 特性 | 方案 A (第三方 API) | 方案 B (本地 ROCm) |
|------|---------------------|---------------------|
| **VLM 位置** | 云端 (OpenAI/阿里云) | 本地 Strix Halo |
| **OCR 位置** | 本地 ROCm 加速 | 本地 ROCm 加速 |
| **需要 vLLM** | ❌ 不需要 | ✅ 需要 |
| **ROCm 兼容性** | ✅ 仅 OCR 使用 ROCm，兼容性好 | ⚠️ vLLM 需要 Triton 补丁 |
| **部署难度** | 简单 | 复杂 |
| **网络依赖** | 需要稳定网络 | 可离线运行 |
| **API 费用** | 按量付费 | 无 |
| **数据隐私** | 文档上传至第三方 | 完全本地 |
| **性能** | 依赖网络延迟 | 纯本地，延迟低 |

### 选择建议

- **推荐方案 A**：适合大多数用户，部署简单，无需处理 ROCm 兼容性问题
- **选择方案 B**：仅当需要完全离线运行或有数据隐私要求时

---

## 交付物

本次部署包含以下文件：

| 文件 | 路径 | 说明 |
|------|------|------|
| **部署指南** | `docs/deployment/strix-halo/deployment.md` | 本文件 |
| **方案 A Compose** | `docs/deployment/strix-halo/compose-scheme-a.yml` | 方案 A Compose |
| **方案 B Compose** | `docs/deployment/strix-halo/compose-scheme-b.yml` | 方案 B Compose |
| **方案 A Dockerfile** | `docs/deployment/strix-halo/Dockerfile-scheme-a` | 方案 A Dockerfile |
| **方案 B Dockerfile** | `docs/deployment/strix-halo/Dockerfile-scheme-b` | 方案 B Dockerfile |

> **注意**：官方目前**没有提供 mineru-rocm 预编译镜像**。对于 AMD ROCm 平台，需要基于 `rocm/pytorch` 官方镜像自行构建。

---

## 方案 A：纯第三方 API (推荐)

### 架构

```
输入 PDF
    ↓
┌─────────────────────────────────────────┐
│           MinerU 混合模式                │
│  ┌─────────────────────────────────┐   │
│  │      本地 OCR (PaddleOCR)        │   │
│  │  ┌─────────┐  ┌──────────────┐  │   │
│  │  │ 文本检测 │→ │ 文本识别      │  │   │
│  │  │ (PyTorch)│  │ (PyTorch)    │  │   │
│  │  └─────────┘  └──────────────┘  │   │
│  │         ↓ ROCm 加速              │   │
│  └─────────────────────────────────┘   │
│         ↓ 识别结果                      │
│  ┌─────────────────────────────────┐   │
│  │      远程 VLM (第三方 API)       │   │
│  │  ┌──────────────────────────┐   │   │
│  │  │ 版面分析                 │   │   │
│  │  │ • 标题/段落/表格位置     │   │   │
│  │  │ • 表格结构识别           │   │   │
│  │  │ • 图片理解               │   │   │
│  │  └──────────────────────────┘   │   │
│  │         ↑ 通过 HTTP API 调用    │   │
│  └─────────────────────────────────┘   │
│         ↓                               │
│    合并结果 → 输出结构化文档           │
└─────────────────────────────────────────┘
```

### 本地 OCR 的 ROCm 支持情况

**本地 OCR 基于 PyTorch，PyTorch 原生支持 ROCm，因此 ROCm 兼容性良好**。

#### 技术细节

| 组件 | 框架 | ROCm 支持 | 说明 |
|------|------|----------|------|
| **MinerU OCR** | PyTorch | ✅ 原生支持 | 使用 `rocm/pytorch` 镜像 |
| **底层实现** | PaddleOCR PyTorch 版 | ✅ 兼容 | 非原生 PaddlePaddle |
| **ONNX Runtime** | onnxruntime-rocm | ✅ 支持 | 可能需要额外安装 |

#### 为什么兼容性好？

1. **PyTorch 官方支持 ROCm**：AMD 和 PyTorch 团队共同维护 ROCm 后端
2. **OCR 模型简单**：PaddleOCR 的模型结构相对简单，使用的都是标准 PyTorch 算子
3. **无自定义 CUDA 内核**：不像 vLLM 那样需要特定的 CUDA/ROCm 内核优化

#### 潜在限制

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| **ONNX Runtime** | 某些 OCR 组件可能使用 ONNX | 安装 `onnxruntime-rocm` 包 |
| **算子回退** | 极少数算子可能回退到 CPU | 性能略有下降，但功能正常 |
| **显存分配** | ROCm 显存管理不如 CUDA 成熟 | 使用 `expandable_segments:True` |

#### 验证 ROCm 工作

```bash
# 进入容器
docker compose exec mineru-hybrid bash

# 检查 PyTorch 是否能识别 AMD GPU
python -c "
import torch
print('PyTorch version:', torch.__version__)
print('CUDA/ROCm available:', torch.cuda.is_available())
print('Device count:', torch.cuda.device_count())
print('Device name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')
print('Current device:', torch.cuda.current_device())
"

# 测试 OCR 性能
# 如果显示 AMD GPU 且 OCR 运行正常，说明 ROCm 工作正常
```

#### 性能预期

在 Strix Halo (Radeon 8060S) 上：
- **文本检测**：约 50-100 ms/页
- **文本识别**：约 100-200 ms/页
- **总 OCR 时间**：约 0.2-0.5 秒/页（取决于内容密度）

> **注意**：如果 OCR 速度明显慢于上述预期（如 >2 秒/页），可能是 ROCm 未正确启用，回退到了 CPU 模式。

---

### 方案 A 特点

- ✅ **无需 vLLM**：本地只运行 OCR (PyTorch)
- ✅ **部署简单**：无需处理 ROCm 兼容性问题
- ✅ **资源占用低**：本地只需 2-4GB 显存用于 OCR
- ✅ **ROCm 支持良好**：本地 OCR 基于 PyTorch，PyTorch 原生支持 ROCm，无兼容性问题
- ⚠️ **需要网络**：依赖第三方 API 可用性
- ⚠️ **API 费用**：按使用量付费

### 快速部署

```bash
# 1. 准备目录
mkdir -p ~/mineru-strix-halo && cd ~/mineru-strix-halo
mkdir -p input output models cache

# 2. 复制方案 A 文件
cp /path/to/strix-halo-compose-scheme-a.yml ./docker-compose.yml
cp /path/to/strix-halo-Dockerfile-scheme-a ./Dockerfile

# 3. 配置环境变量
cat > .env << 'EOF'
MINERU_VLM_API_KEY=your-api-key
MINERU_VLM_BASE_URL=https://api.openai.com/v1
MINERU_VLM_MODEL=gpt-4o
EOF

# 4. 构建并启动
docker build -t mineru-rocm:latest -f Dockerfile .
docker compose up -d

# 5. 使用
cp your.pdf input/
docker compose exec mineru-hybrid \
    mineru -p /input/your.pdf -o /output/ -b hybrid-http-client
```

---

## 方案 B：本地 ROCm 推理 (高级)

### 架构

```
输入 PDF
    ↓
┌─────────────────────────────────────────┐
│           MinerU 本地模式                │
│  ┌─────────────────────────────────┐   │
│  │      本地 OCR (PaddleOCR)        │   │
│  │  ┌─────────┐  ┌──────────────┐  │   │
│  │  │ 文本检测 │→ │ 文本识别      │  │   │
│  │  │ (PyTorch)│  │ (PyTorch)    │  │   │
│  │  └─────────┘  └──────────────┘  │   │
│  │         ↓ ROCm 加速              │   │
│  └─────────────────────────────────┘   │
│         ↓ 识别结果                      │
│  ┌─────────────────────────────────┐   │
│  │      本地 VLM (vLLM on ROCm)     │   │
│  │  ┌──────────────────────────┐   │   │
│  │  │ 版面分析                 │   │   │
│  │  │ • 标题/段落/表格位置     │   │   │
│  │  │ • 表格结构识别           │   │   │
│  │  │ • 图片理解               │   │   │
│  │  └──────────────────────────┘   │   │
│  │         ↑ 本地 vLLM 推理        │   │
│  └─────────────────────────────────┘   │
│         ↓                               │
│    合并结果 → 输出结构化文档           │
└─────────────────────────────────────────┘
```

### 特点

- ✅ **完全离线**：无需网络，数据不出本地
- ✅ **无 API 费用**：一次性投入硬件成本
- ✅ **低延迟**：纯本地处理，无网络延迟
- ⚠️ **需要 vLLM**：必须解决 ROCm 兼容性问题
- ⚠️ **部署复杂**：需要 Triton 补丁和手动调优
- ⚠️ **资源占用高**：需要 16GB+ 显存用于 VLM

### 已知问题

vLLM 在 ROCm 上存在性能问题：
- **MIOpen 库缺少 Conv3d(bfloat16) 优化内核**
- 导致卷积计算回退到通用实现
- **解决方案**：需要应用社区 Triton 补丁

参考：`src/docs/zh/usage/acceleration_cards/AMD.md`

### 快速部署

```bash
# 1. 准备目录
mkdir -p ~/mineru-strix-halo && cd ~/mineru-strix-halo
mkdir -p input output models cache

# 2. 复制方案 B 文件
cp /path/to/strix-halo-compose-scheme-b.yml ./docker-compose.yml
cp /path/to/strix-halo-Dockerfile-scheme-b ./Dockerfile

# 3. 构建镜像（包含 vLLM）
docker build -t mineru-rocm-vllm:latest -f Dockerfile .

# 4. 启动服务（包含 VLM 服务器和 MinerU）
docker compose up -d

# 5. 等待 VLM 服务启动（约 2-3 分钟）
docker compose logs -f mineru-vlm-server

# 6. 使用（连接到本地 vLLM）
cp your.pdf input/
docker compose exec mineru-local \
    mineru -p /input/your.pdf -o /output/ -b hybrid-http-client
```

### 方案 B 服务说明

方案 B 包含两个服务：

| 服务 | 名称 | 端口 | 说明 |
|------|------|------|------|
| `mineru-vlm-server` | VLM 推理服务 | 8000 | 本地 vLLM 服务器 |
| `mineru-local` | MinerU 主服务 | - | 使用本地 VLM |

---

## 硬件要求

- **CPU**: AMD Strix Halo (Ryzen AI Max+ 395 或类似)
- **GPU**: 集成 Radeon 8060S (40 CU)
- **内存**: 32GB+ 推荐
- **存储**: 10GB+ 可用空间 (方案 A) / 50GB+ (方案 B，含 VLM 模型)
- **操作系统**: Linux (Ubuntu 22.04/24.04 推荐)

## 软件要求

- Docker 20.10+
- Docker Compose 2.0+
- ROCm 6.2+ 或 6.3+ (主机端)

---

## 通用部署步骤

### 1. 安装 ROCm (主机端)

```bash
# 添加 ROCm 仓库
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/latest ubuntu main' | sudo tee /etc/apt/sources.list.d/rocm.list

# 安装 ROCm
sudo apt update
sudo apt install -y rocm-dev rocm-utils

# 验证安装
rocminfo | grep gfx
# 应该显示 gfx1150 (Strix Halo)
```

### 2. 配置 Docker 使用 ROCm

```bash
# 安装 Docker (如果尚未安装)
curl -fsSL https://get.docker.com | sh

# 添加用户到 docker 和 render 组
sudo usermod -aG docker,render,video $USER
newgrp docker

# 验证 Docker ROCm 支持
docker run -it --rm --device=/dev/kfd --device=/dev/dri --group-add video --group-add render rocm/pytorch:rocm6.2_ubuntu22.04_py3.10 rocm-smi
```

---

## 性能优化

### Strix Halo 特定优化

```bash
# 在 .env 中添加
HSA_OVERRIDE_GFX_VERSION=11.5.0
OMP_NUM_THREADS=16
PYTORCH_HIP_ALLOC_CONF=expandable_segments:True
```

### ROCm 环境变量

| 变量 | 说明 | 推荐值 |
|------|------|--------|
| `HSA_OVERRIDE_GFX_VERSION` | 覆盖 GPU 架构版本 | 11.5.0 (Strix Halo) |
| `OMP_NUM_THREADS` | OpenMP 线程数 | 16 (根据 CPU 核心调整) |
| `PYTORCH_HIP_ALLOC_CONF` | PyTorch 内存配置 | expandable_segments:True |

---

## 故障排除

### 问题 1: ROCm 设备无法访问

```bash
# 检查设备权限
ls -la /dev/kfd /dev/dri/

# 修复权限
sudo chmod 666 /dev/kfd
sudo chmod 666 /dev/dri/render*
sudo chmod 666 /dev/dri/card*
```

### 问题 2: 模型下载失败

```bash
# 手动下载模型
docker compose exec mineru-hybrid mineru-models-download -s modelscope -m pipeline

# 检查模型目录
ls -la models/
```

### 问题 3: OCR 速度较慢

```bash
# 检查 ROCm 是否正常工作
docker compose exec mineru-hybrid python -c "
import torch
print('PyTorch version:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
print('Device count:', torch.cuda.device_count())
print('Device name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')
"
```

### 问题 4: VLM API 连接失败 (方案 A)

```bash
# 测试 API 连接
docker compose exec mineru-hybrid curl \
  -H "Authorization: Bearer ${MINERU_VLM_API_KEY}" \
  -H "Content-Type: application/json" \
  ${MINERU_VLM_BASE_URL}/models
```

### 问题 5: 本地 vLLM 启动失败 (方案 B)

```bash
# 查看 vLLM 服务器日志
docker compose logs -f mineru-vlm-server

# 常见问题：
# 1. 显存不足 - 降低 gpu-memory-utilization
# 2. Triton 内核错误 - 需要应用 AMD 社区补丁
# 3. 模型下载失败 - 检查网络连接
```

---

## 文件结构

```
~/mineru-strix-halo/
├── docker-compose.yml          # Docker Compose 配置 (根据方案选择)
├── Dockerfile                  # ROCm 镜像构建文件 (根据方案选择)
├── .env                        # 环境变量 (API 密钥等)
├── input/                      # 输入 PDF 文件
├── output/                     # 输出结果
├── models/                     # 本地模型缓存
│   ├── OCR/                    # OCR 模型 (约 500MB)
│   ├── VLM/                    # VLM 模型 (方案 B，约 15GB)
│   └── ...
└── cache/                      # 其他缓存
```

---

## 常用命令

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 查看日志
docker compose logs -f

# 进入容器
docker compose exec mineru-hybrid bash
# 或 (方案 B)
docker compose exec mineru-local bash

# 重启
docker compose restart

# 清理缓存
docker compose exec mineru-hybrid rm -rf /root/.cache/mineru/*
```

---

## 参考

- [ROCm 官方文档](https://rocm.docs.amd.com/)
- [Strix Halo 技术规格](https://www.amd.com/en/products/processors/consumer/ryzen-ai.html)
- [MinerU 官方文档](https://github.com/opendatalab/MinerU)
- [AMD ROCm Docker 指南](https://hub.docker.com/r/rocm/pytorch)
- [MinerU AMD ROCm 社区适配](src/docs/zh/usage/acceleration_cards/AMD.md)
