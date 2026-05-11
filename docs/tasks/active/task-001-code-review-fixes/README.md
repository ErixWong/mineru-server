# Task-001: Code Review Fixes

## 目标

修复代码审计中发现的问题，确保生产环境稳定运行。

## 审计时间

2026-05-11

## 审计范围

| 文件 | 类型 | 风险等级 |
|------|------|----------|
| processor.py | 修改 | 高 |
| mineru_worker.py | 新增 | 高 |
| file_manager.py | 修改 | 中 |
| api.py | 修改 | 低 |
| app.py | 修改 | 低 |

## 审计发现详情

### P0 - 紧急问题

#### 1. mineru_worker.py 无异常处理 (Line 11-43)

**问题描述**：
```python
if __name__ == '__main__':
    config = json.load(sys.stdin)
    from mineru.cli.common import do_parse
    do_parse(...)
    print("DONE")
```

整个 worker 脚本没有任何异常处理。任何错误都会直接 crash，stderr 虽然会被 subprocess 捕获，但：
- 错误信息可能不完整
- 无法区分"正常完成"和"异常退出"
- 调试困难

**影响**：
- 生产环境中任务失败时难以定位原因
- processor.py 无法获取完整错误信息

**修复方案**：
```python
if __name__ == '__main__':
    try:
        config = json.load(sys.stdin)
        from mineru.cli.common import do_parse
        
        pdf_path = Path(config['pdf_path'])
        pdf_bytes = pdf_path.read_bytes()
        
        do_parse(...)
        print("DONE")
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON config: {e}", file=sys.stderr)
        sys.exit(1)
    except ImportError as e:
        print(f"ERROR: MinerU import failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
```

### P1 - 高风险问题

#### 2. processor.py 临时文件泄漏 (Line 119-156)

**问题描述**：
```python
temp_pdf = PathLib(task_dir) / "_temp_input.pdf"
temp_pdf.write_bytes(pdf_bytes)
# ... subprocess 执行 ...
if temp_pdf.exists():
    temp_pdf.unlink()
```

如果 subprocess 在清理前崩溃（OOM、信号中断、超时等），`_temp_input.pdf` 不会被删除。

**影响**：
- 磁盘空间泄漏
- 多次失败后可能耗尽存储

**修复方案**：
```python
temp_pdf = Path(task_dir) / "_temp_input.pdf"
temp_pdf.write_bytes(pdf_bytes)
try:
    result = await asyncio.to_thread(subprocess.run, ...)
    # ... 处理结果 ...
finally:
    if temp_pdf.exists():
        temp_pdf.unlink()
```

#### 3. 后端目录映射不一致风险 (file_manager.py:128-139 vs processor.py)

**问题描述**：

`file_manager.py` 中 `backend_map` 定义：
```python
backend_map = {
    "vlm-auto-engine": "vlm",
    "pipeline": "auto",
    # ...
}
backend_type = backend_map.get(backend, "auto")
output_dir = task_dir / pdf_name / backend_type
```

但 MinerU 的 `do_parse` 函数可能使用不同的目录命名规则。如果 MinerU 实际输出目录与预期不一致：
- `processor.py:168-169` 的输出验证会失败
- 任务会被标记为 failed，即使实际成功

**需要确认**：
1. MinerU `do_parse` 如何确定输出子目录名？
2. 是用 `backend` 参数还是内部的 `parse_method`？

**验证方法**：
```bash
# 运行测试，检查实际输出目录
cd mcp-server
python -c "
from mineru.cli.common import do_parse
# 测试不同 backend 的输出目录结构
"
```

### P2 - 中风险问题

#### 4. processor.py Path 别名冗余 (Line 115)

**问题描述**：
```python
from pathlib import Path as PathLib  # Line 115
# 但文件顶部已有：
from pathlib import Path  # Line 8
```

`PathLib` 别名完全冗余，增加代码混淆。

**修复**：直接使用 `Path`，删除 `PathLib` 别名。

#### 5. processor.py 延迟导入 (Line 166)

**问题描述**：
```python
# 在函数内部导入
from .file_manager import FileManager  # Line 166
```

**影响**：
- 降低可读性
- 增加出错概率（循环导入问题时难以定位）

**修复**：移到文件顶部：
```python
# 顶部导入区
from .file_manager import FileManager
```

#### 6. processor.py 超时过长 (Line 151)

**问题描述**：
```python
timeout=3600,  # 1小时
```

**影响**：
- 挂起的任务不会被及时回收
- 资源浪费

**修复方案**：
- 配置化超时时间（通过 config.py）
- 默认改为 1800s (30分钟)

#### 7. api.py debug 日志 (Line 254-256)

**问题描述**：
```python
logger.debug(f"MD path: {md_path}, exists: {md_path.exists()}")
logger.debug(f"MD content length: {len(markdown_content)}")
```

**影响**：
- debug 日志在生产环境默认不显示
- 但保留这些日志有助于问题排查

**建议**：保留但确认用途，或改为 conditional debug。

#### 8. f_make_md_mode 参数值确认

**问题描述**：
`mineru_worker.py:40`：
```python
f_make_md_mode="mm_markdown",
```

需要确认：
- MinerU 的 `do_parse` 是否接受字符串 `"mm_markdown"`？
- 还是需要整数模式码？

**验证方法**：查看 MinerU 源码中 `do_parse` 的参数定义。

### P3 - 低风险/建议

#### 9. app.py 启动提示 (Line 301)

**问题描述**：
```python
print(f"  [!] Server is running. DO NOT CLOSE this window!")
```

`[!]` 符号可能被误解为警告。

**建议**：改为 `[i]` 或去掉符号。

#### 10. processor.py worker_script 路径 (Line 125)

**问题描述**：
```python
worker_script = PathLib(__file__).parent.parent / "mineru_worker.py"
```

相对路径依赖文件位置，打包或移动后会失败。

**建议**：
- 配置化路径
- 或使用 `importlib.resources` 定位

## 补充发现

### worker_script 路径硬编码

**文件**: `processor.py:125`
**问题**: 相对路径计算依赖文件位置，不够健壮
**建议**: 配置化或使用包资源定位

### backend_map 硬编码

**文件**: `file_manager.py:128-139`
**问题**: backend 映射硬编码，MinerU 新增 backend 需同步修改代码
**建议**: 配置文件或动态发现

## 修复顺序

1. **P0**: mineru_worker.py 异常处理
2. **P1**: 临时文件泄漏
3. **P1**: 确认 MinerU 目录结构后修复 backend_map
4. **P2**: PathLib 别名、延迟导入、超时配置化
5. **P3**: 启动提示改进

## 状态

- [x] P0: mineru_worker.py 异常处理 ✅ (PR #2)
- [x] P1: 临时文件泄漏修复 ✅ (PR #2)
- [x] P1: MinerU 目录结构确认 ✅ (PR #3 - 修复 hybrid backend 映射错误)
- [x] P2: PathLib 移除 ✅ (PR #2)
- [x] P2: 延迟导入移到顶部 ✅ (PR #2)
- [x] P2: 超时配置化 ✅ (PR #2, DEFAULT_TIMEOUT=1800)
- [x] P2: debug 日志处理 ✅ (保留，debug级别生产环境不显示)
- [x] P2: f_make_md_mode 兼容性确认 ✅ ("mm_markdown" = MakeMode.MM_MD)
- [x] P3: 启动提示改进 ✅ (PR #2, [!] → [i])
- [ ] P3: worker_script 路径改进 (低优先级，暂不处理)

## 修复记录

### PR #2 (2026-05-11)

修复项:
- mineru_worker.py: 添加完整 try/except 异常处理
- processor.py: try/finally 确保临时文件删除
- processor.py: 移除 PathLib 别名，导入移到顶部
- processor.py: DEFAULT_TIMEOUT = 1800
- app.py: [!] 改为 [i]

### PR #3 (2026-05-11)

修复项:
- file_manager.py: 修正 hybrid backend 输出目录映射
  - hybrid-auto-engine: hybrid_vlm → hybrid_auto
  - hybrid-http-client: hybrid_vlm → hybrid_auto

分析结论:
- MinerU 输出目录结构: {output_dir}/{pdf_name}/{parse_method}/
- vlm backend → vlm/
- pipeline backend → auto/
- hybrid backend → hybrid_auto/
- office backend → office/
- f_make_md_mode="mm_markdown" 正确 (等于 MakeMode.MM_MD)

### PR #4 (2026-05-11)

修复项:
- Dockerfile: 移除 --enable-mineru-api 参数，改为 --mode http --port 8001
- docker/Dockerfile.all-in-one: 同上
- docker/Dockerfile.mcp-only: 简化 CMD
- docker/docker-compose.yml: 使用根目录 Dockerfile (git clone 方式)
- docker/README.md: 更新启动命令示例

分析结论:
- CLI 只支持: --mode, --host, --port, --log-level, --no-api, --no-mcp
- --enable-mineru-api 参数不存在（已废弃）
- docker-compose.yml 应使用根目录 Dockerfile（git clone 方式，无需本地 MinerU 源码）

## 相关文件

- `mcp-server/src/mineru_mcp/task_queue/processor.py`
- `mcp-server/src/mineru_mcp/mineru_worker.py`
- `mcp-server/src/mineru_mcp/task_queue/file_manager.py`
- `mcp-server/src/mineru_mcp/api.py`
- `mcp-server/src/mineru_mcp/app.py`