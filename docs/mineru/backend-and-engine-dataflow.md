# MinerU Backend 与推理引擎数据链路

## 1. 先分清两层概念

MinerU 的运行模式要分成两层理解，否则很容易把 `backend` 和 `engine` 混在一起：

- `backend`：业务入口层。由 `--backend` 参数或 API 入参决定，例如 `pipeline`、`vlm-auto-engine`、`hybrid-http-client`。
- `engine`：本地 VLM 的具体推理执行引擎，例如 `transformers`、`vllm`、`lmdeploy`、`mlx`。

核心关系如下：

- `pipeline` 不使用 VLM engine。
- `*-http-client` 不在本地执行 VLM engine，而是调用远程 OpenAI-compatible 服务。
- `*-auto-engine` 会先进入“本地 VLM”路径，再由 MinerU 自动选择具体 engine。
- `vlm-vllm-engine`、`vlm-vllm-async-engine`、`vlm-lmdeploy-engine` 这类 backend，则是直接指定 engine。

## 2. Backend 模式总览

### 2.1 `pipeline`

传统流水线，不使用 VLM。

适用场景：

- 多语言文档
- 不依赖远程或本地大模型
- 更稳定的纯结构化解析链路

数据链路：

```text
PDF/图片
  -> 本地 OCR / layout / formula / table 模型
  -> 结构化中间结果
  -> markdown / json 输出
```

### 2.2 `vlm-http-client`

本地不加载 VLM，通过 HTTP 调用远程 OpenAI-compatible 服务。

适用场景：

- 本地机器不适合承载 VLM
- 希望将 VLM 推理外置为独立服务

数据链路：

```text
PDF/图片
  -> 本地预处理 / 切页 / 图像准备
  -> 通过 HttpVlmClient 组装请求
  -> POST 到远程 OpenAI-compatible VLM 服务
  -> 接收模型响应
  -> 后处理
  -> markdown / json 输出
```

### 2.3 `hybrid-http-client`

本地执行 OCR、布局、表格等传统能力，VLM 相关部分走远程服务。

适用场景：

- 多语言支持优先
- 降低本地 GPU 依赖
- 当前项目推荐模式

数据链路：

```text
PDF/图片
  -> 本地 OCR / layout / formula / table
  -> 需要 VLM 判断的区域或页面
  -> 调远程 OpenAI-compatible VLM 服务
  -> 合并本地结构结果与远程 VLM 结果
  -> markdown / json 输出
```

### 2.4 `vlm-auto-engine`

本地 VLM 模式，但具体使用哪个本地 engine，由 MinerU 在运行时自动选择。

这个 backend 的真实含义是：

- `backend` 已固定为“本地 VLM”
- `engine` 由运行时环境决定

它不等于：

- 必定使用 `vllm`
- 必定启动一个独立的 `vllm serve`
- 必定使用 `transformers`
- 只要选中就一定跑在 GPU 上

数据链路：

```text
PDF/图片
  -> 进入本地 VLM 路径
  -> get_vlm_engine("auto")
  -> 自动探测本机可用 engine
     -> Linux: vllm -> lmdeploy -> transformers
     -> Windows: lmdeploy -> transformers
     -> macOS: mlx -> transformers
  -> 选中 engine 后在本地执行推理
  -> 后处理
  -> markdown / json 输出
```

### 2.5 `hybrid-auto-engine`

本地 OCR + 本地 VLM，VLM 的具体引擎同样由运行时自动选择。

数据链路：

```text
PDF/图片
  -> 本地 OCR / layout / formula / table
  -> 需要 VLM 的部分
  -> get_vlm_engine("auto")
  -> 自动选择本地 engine
  -> 合并结果
  -> markdown / json 输出
```

### 2.6 `vlm-vllm-engine`

本地 VLM，明确指定使用 `vllm` 同步引擎。

### 2.7 `vlm-vllm-async-engine`

本地 VLM，明确指定使用 `vllm` 异步引擎。

适用场景：

- 更偏服务化
- 高并发场景
- Router / worker 体系

### 2.8 `vlm-lmdeploy-engine`

本地 VLM，明确指定使用 `lmdeploy`。

## 3. `vlm-auto-engine` 的自动选择逻辑

上游 MinerU 在 `mineru/utils/engine_utils.py` 中实现了自动选择逻辑。

逻辑摘要：

```text
if inference_engine == "auto":
  Linux:
    try import vllm -> 选择 vllm-engine / vllm-async-engine
    except:
      try import lmdeploy -> 选择 lmdeploy-engine
      except:
        选择 transformers

  Windows:
    try import lmdeploy -> 选择 lmdeploy-engine
    except:
      选择 transformers

  macOS:
    try import mlx_vlm 且系统版本满足条件 -> 选择 mlx-engine
    except:
      选择 transformers
```

这意味着：

- `vlm-auto-engine` 的“auto”是对本地 engine 的自动选择，不是对业务 backend 的自动选择。
- 在 Linux 上，只要当前 Python 环境里 `import vllm` 成功，优先级就高于 `lmdeploy` 和 `transformers`。
- 如果 `vllm` 没安装、导入失败或依赖不完整，才会退回下一级。

## 4. `vllm` 在 MinerU 里到底是什么

`vllm` 在 MinerU 里主要有两种使用形态：

### 4.1 进程内直调 `vllm` Python 包

这是本地同步/异步 vLLM backend 的核心实现方式。

在 `mineru/backend/vlm/vlm_analyze.py` 中：

- `vllm-engine` 通过 `import vllm` 后直接实例化 `vllm.LLM(**kwargs)`
- `vllm-async-engine` 通过 `AsyncLLM.from_engine_args(...)` 创建异步引擎

这条路径的特点：

- 不依赖外部 HTTP 服务
- 不需要先单独启动 `vllm serve`
- 由 MinerU 当前 Python 进程直接持有 `vllm` 对象并完成推理

### 4.2 包装成独立 `vllm server`

MinerU 也提供 `mineru-vlm-server -e vllm` 命令。

这条命令在 `mineru/model/vlm/vllm_server.py` 中实现，本质是：

- 调用 `vllm.entrypoints.cli.main`
- 将参数重写为 `serve <model> ...`
- 直接启动 `vllm` 的 server 模式

这意味着：

- 它仍然依赖已安装的 `vllm` Python 包
- 只是从“进程内直调”变成“启动独立 server 进程”

## 5. `vllm` 模式的数据链路

### 5.1 `vlm-vllm-engine`

本地同步 vLLM。

数据链路：

```text
任务输入（PDF / 图片）
  -> MinerU 解析入口
  -> backend = vlm-vllm-engine
  -> ModelSingleton.get_model(...)
  -> import vllm
  -> 创建 vllm.LLM(...)
  -> 构造 MinerUClient(backend="vllm-engine", vllm_llm=...)
  -> 文档切页 / 图像准备
  -> 调用 vllm.LLM 做本地推理
  -> 拿到模型输出
  -> 转换为 middle_json / content_list / markdown
  -> 产出最终文件
```

关键点：

- VLM 推理发生在 MinerU 当前 Python 进程内
- `vllm` 作为 Python 库被直接调用
- 不是通过 HTTP 回环调用自己

### 5.2 `vlm-vllm-async-engine`

本地异步 vLLM。

数据链路：

```text
任务输入（PDF / 图片）
  -> MinerU 解析入口
  -> backend = vlm-vllm-async-engine
  -> ModelSingleton.get_model(...)
  -> 导入 AsyncEngineArgs / AsyncLLM
  -> 创建 AsyncLLM.from_engine_args(...)
  -> 构造 MinerUClient(backend="vllm-async-engine", vllm_async_llm=...)
  -> 文档切页 / 图像准备
  -> 通过异步 vLLM 引擎执行推理
  -> 拿到模型输出
  -> 后处理并生成结果文件
```

### 5.3 `mineru-vlm-server -e vllm`

独立 server 模式。

数据链路：

```text
mineru-vlm-server -e vllm
  -> MinerU 的 vllm_server 入口
  -> 调用 vllm.entrypoints.cli.main
  -> 启动 vllm serve <model>
  -> 暴露独立服务端口

其他客户端 / MinerU http-client backend
  -> 调用该服务
  -> 服务内由 vllm 负责模型推理
  -> 返回推理结果
```

这条路径和 `vlm-vllm-engine` 的关键区别是：

- `vlm-vllm-engine`：MinerU 当前进程内直接调 `vllm`
- `mineru-vlm-server -e vllm`：MinerU 把 `vllm` 包装成独立服务进程

## 6. 为什么 `vlm-auto-engine` 可能最终走到 `transformers`

如果日志出现：

```text
Using transformers as the inference engine for VLM.
```

说明当前后端虽是本地 VLM，但自动选择最终没有命中 `vllm` 或 `lmdeploy`。

常见原因：

- 当前 Python 环境里没有安装 `vllm`
- `vllm` 已安装，但 `import vllm` 失败
- `lmdeploy` 同样不可用
- 最终回退到 `transformers`

这也是排查 `vlm-auto-engine` 时必须先区分 `backend` 与 `engine` 的原因：

- 任务层面看，backend 仍然是本地 VLM
- 运行层面看，真正执行推理的 engine 可能已经回退成 `transformers`

## 7. 排查本地 VLM 路径时的建议顺序

1. 确认任务记录中的 `backend` 是什么。
2. 查看运行日志中的 engine 选择结果，例如：
   - `Using vllm-engine as the inference engine for VLM.`
   - `Using lmdeploy-engine as the inference engine for VLM.`
   - `Using transformers as the inference engine for VLM.`
3. 如果是本地 engine，继续检查：
   - GPU 是否对容器可见
   - `torch.cuda.is_available()` 是否为 `True`
   - 对应 engine 的依赖是否真的已安装且可导入
4. 如果 `auto-engine` 回退到了 `transformers`，优先检查 `vllm` / `lmdeploy` 是否可用，而不是先怀疑 backend 参数没有生效。

## 8. 当前项目的落地要求

对于当前 `erix-mineru` 项目，要让 `vlm-auto-engine` 在 Linux 容器内优先走进程内 `vllm`，至少需要满足以下条件：

1. 镜像安装 MinerU 时必须包含 `vllm` 扩展，而不是仅安装 `mineru[core]`。
2. 容器内 `import vllm` 必须成功。
3. 宿主机 NVIDIA 驱动必须兼容镜像内的 CUDA / PyTorch / vLLM 运行时。
4. 本地 GPU 对容器可见，且 Python 侧 `torch.cuda.is_available()` 为 `True`。
5. 初始并发建议收紧，避免在排障阶段被多任务争抢显存和 worker 堆积干扰判断。

当前项目的 Docker 路线中，如果镜像只安装 `mineru[core]`，则 `vlm-auto-engine` 在 Linux 下会按照上游逻辑自动退回到 `transformers`，继而触发 `transformers` / `triton` 路径的运行时编译要求。这也是此前“选了本地 VLM，但实际没有走进程内 vLLM”的直接原因。

## 9. 一句话总结

- `backend` 决定业务路径：本地 VLM、远程 VLM、纯 pipeline，还是 hybrid。
- `engine` 决定本地 VLM 具体由谁执行：`vllm`、`lmdeploy`、`transformers`、`mlx`。
- `vlm-auto-engine` 的本质是“本地 VLM + 自动选 engine”。
- MinerU 的 `vllm` 既可以作为库被当前进程直接调用，也可以被包装成独立 server 运行。
