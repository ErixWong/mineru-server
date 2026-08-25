# Local GPU VLM Deployment (vLLM) — Known Pitfalls & Fixes

> 面向在自建 GPU 主机上用 `docker-compose.yml` 部署 MinerU2.5 VLM 模型的部署者。
> 本文记录 vLLM 本地 serve MinerU2.5-Pro 系列模型时的两个已知坑及修复方案。

## 背景

`docker-compose.yml` 默认的 remote-VLM 模式包含 `vlm-server` 服务：

- 镜像：`vllm/vllm-openai:v0.21.0`（官方 vLLM OpenAI 兼容服务）
- 模型：`MinerU2.5-Pro-2605-1.2B`（或通过 `VLLM_MODEL_PATH` / `VLLM_SERVED_MODEL_NAME` 覆盖）
- `mineru-mcp` 通过 `MINERU_VL_SERVER=http://vlm-server:30000/v1` 访问它

直接使用官方 vLLM 镜像裸跑该模型会出现两类问题，本仓库已通过
`scripts/vlm-server-entrypoint.sh` + compose 参数内置修复。

## 坑 1：transformers 版本不兼容导致 VLM 输出乱码

### 症状

- 任务能正常提交、vLLM 收到请求且返回 200
- 但生成内容为乱码（多语言混杂、升序 ASCII 序列等），`finish_reason: length`
- `vlm-http-client` / `hybrid-http-client` 任务全部**空块**（117 页 PDF 输出 0 个块）
- CPU 用 transformers 直跑模型正常，但 vLLM 输出乱码 → 不是模型问题

### 根因

`vllm/vllm-openai:v0.21.0` 镜像自带 **transformers 5.8.1**，而 MinerU2.5 系列模型
（如 `MinerU2.5-Pro-2605-1.2B`）是用 **transformers 4.57.x** 训练的。

transformers 5.x 加载这类模型时 `tie_word_embeddings` 静默失效：
`lm_head` 被随机初始化（日志出现 `MISSING: lm_head.weight ... newly initialized`），
语言模型头输出错误 token → 生成乱码。

### 验证方法

```python
# 在两个 transformers 版本下分别加载模型，比较 tie 是否生效
import torch
from transformers import Qwen2VLForConditionalGeneration
model = Qwen2VLForConditionalGeneration.from_pretrained("<model_dir>", trust_remote_code=True)
print(torch.equal(model.get_input_embeddings().weight, model.get_output_embeddings().weight))
# 4.57.x → True（正常）；5.8.1 → False（坏）
```

### 修复

entrypoint 在启动 vLLM 前将 transformers 固定为 `4.57.6`（vLLM 0.21 约束为
`transformers>=4.56.0` 且 `!=5.0-5.5.0`，4.57.6 满足）：

```sh
pip install -q --no-cache-dir "transformers==4.57.6"
```

## 坑 2：缺 MinerULogitsProcessor 导致布局输出重复/无法解析

### 症状

即使 transformers 版本正确，若 vLLM 未启用 logits processor，生成的布局 JSON
会重复 n-gram，MinerU 无法解析出有效块（任务同样空块或块内容异常）。

### 根因

MinerU 上游的 vLLM 启动包装（`mineru/model/vlm/vllm_server.py`）会向 vLLM 命令
追加：

```
--logits-processors mineru_vl_utils:MinerULogitsProcessor
```

`MinerULogitsProcessor`（`VllmV1NoRepeatNGramLogitsProcessor`）在生成布局 JSON
时禁止重复 n-gram。该处理器来自 `mineru-vl-utils` 包，**不在官方 vllm 镜像里**，
且 compose 模板原先没有把参数传进去。

### 修复

1. entrypoint 安装 `mineru-vl-utils`（提供处理器类）：

```sh
pip install -q --no-cache-dir "mineru-vl-utils>=1.0.5,<2"
```

2. compose 的 `vlm-server.command` 增加：

```
- --logits-processors
- mineru_vl_utils:MinerULogitsProcessor
```

## 坑 3：ModelScope 新缓存布局路径

### 症状

vLLM 报模型路径不存在 / 加载失败。

### 根因

ModelScope 新缓存布局（`modelscope>=1.x` 新版本）：

```
/root/.cache/modelscope/models/OpenDataLab--MinerU2.5-Pro-2605-1.2B/snapshots/master
```

注意是**双横线** `OpenDataLab--MinerU2.5...` + `snapshots/master` 层级，
与旧布局 `models/OpenDataLab/MinerU2.5-Pro-2605-1.2B`（单斜杠）不同。

### 修复

compose 默认值已改为新布局；若你的缓存是旧布局，用环境变量覆盖：

```bash
VLLM_MODEL_PATH=/root/.cache/modelscope/models/OpenDataLab/MinerU2.5-Pro-2605-1.2B docker compose up -d
```

## 验证清单

部署后建议按以下步骤验证，避免"任务 completed 但全空块"的假成功：

```bash
# 1. vLLM 健康 + 模型名
curl http://localhost:30000/v1/models

# 2. 纯文本请求应返回正常内容（非乱码）
curl http://localhost:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"MinerU2.5-Pro-2605-1.2B","messages":[{"role":"user","content":"hello"}],"max_tokens":32}'
# 若内容为多语言混杂乱码 → 坑 1 未修复（检查 transformers 版本）

# 3. 提交一个含图表的 PDF 任务，确认 vLLM 收到 POST 且输出非空块
```

## 相关文件

| 文件 | 作用 |
| --- | --- |
| `scripts/vlm-server-entrypoint.sh` | vLLM 启动前修复（降级 transformers + 装 mineru-vl-utils） |
| `docker-compose.yml` | vlm-server 服务定义（entrypoint / logits-processors / 路径默认值） |
