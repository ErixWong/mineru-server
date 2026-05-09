# Backend 参数处理逻辑确认

**问题**: Backend 可以通过请求构造吗？还是在配置文件里设好就不能改？

**答案**: ✅ **可以通过请求动态覆盖配置中的默认 backend！**

---

## 1. 配置文件中的默认 Backend

**位置**: `mcp-server/src/mineru_mcp/config.py`

**环境变量**: `MINERU_DEFAULT_BACKEND`

**默认值**: `"hybrid-http-client"`

**配置读取逻辑**：
```python
default_backend = os.getenv("MINERU_DEFAULT_BACKEND", DEFAULT_BACKEND)
if default_backend not in VALID_BACKENDS:
    default_backend = DEFAULT_BACKEND
```

**有效 Backend 列表**：
- `pipeline` - 传统 pipeline（无 VLM，多语言支持）
- `vlm-auto-engine` - 本地 VLM 引擎（仅中英文）
- `vlm-http-client` - 远程 VLM（OpenAI-compatible）
- `hybrid-auto-engine` - 本地 OCR + 本地 VLM（多语言）
- `hybrid-http-client` - 本地 OCR + 远程 VLM（多语言，推荐）

---

## 2. MCP Tools 中的 Backend 处理

**位置**: `mcp-server/src/mineru_mcp/server.py`

**处理逻辑**：
```python
# parse_pdf 和 submit_task 的处理逻辑相同
effective_backend = backend if backend is not None else config.default_backend
validated_backend = validate_backend(effective_backend)
```

**关键点**：
- ✅ 如果请求传入 `backend` 参数 → 使用请求中的 backend
- ✅ 如果请求未传入 `backend`（为 None） → 使用配置中的 `default_backend`
- ✅ 使用前会验证 backend 是否在有效列表中

**示例**：

**请求传入 backend**：
```json
{
  "method": "parse_pdf",
  "params": {
    "file_base64": "...",
    "backend": "pipeline"  // ✅ 覆盖配置，使用 pipeline
  }
}
```

**请求不传入 backend**：
```json
{
  "method": "parse_pdf",
  "params": {
    "file_base64": "..."  // 使用配置中的 default_backend
  }
}
```

---

## 3. REST API 中的 Backend 处理

**位置**: `mcp-server/src/mineru_mcp/api.py`

**处理逻辑**：
```python
@app.post("/parse")
async def parse_pdf_sync(
    backend: str = Form(default="hybrid-http-client"),  # ⚠️ 硬编码默认值
    ...
):
    validated_backend = validate_backend(backend)
```

**关键点**：
- ⚠️ REST API 使用硬编码的默认值 `"hybrid-http-client"`
- ⚠️ **没有从配置文件读取 default_backend**
- ⚠️ 这与 MCP Tools 的处理不一致

**问题**: REST API 应该从配置中读取默认值，而不是硬编码！

---

## 4. 问题发现和建议修复

### 4.1 当前问题

**不一致性**：
- ✅ MCP Tools: 使用 `config.default_backend`（从环境变量读取）
- ❌ REST API: 硬编码 `"hybrid-http-client"`（不从配置读取）

**影响**：
- 用户修改 `MINERU_DEFAULT_BACKEND` 环境变量 → MCP Tools 会生效
- 用户修改 `MINERU_DEFAULT_BACKEND` 环境变量 → REST API 不生效（始终使用硬编码值）

---

### 4.2 建议修复

**修改 REST API**：

**当前代码**（api.py）：
```python
backend: str = Form(default="hybrid-http-client"),  # ❌ 硬编码
```

**建议修改**：
```python
# 方案 1: 从配置读取（推荐）
config = get_config()
backend: str = Form(default=config.default_backend),  # ✅ 从配置读取

# 方案 2: 支持可选参数（更灵活）
backend: Optional[str] = Form(default=None),  # ✅ 可选参数
if backend is None:
    backend = config.default_backend  # 从配置读取
```

---

## 5. 总结

**当前状态**：

| API | Backend 参数 | 是否可覆盖 | 默认值来源 | 是否一致 |
|-----|-------------|----------|-----------|---------|
| **MCP Tools** | ✅ 可选 | ✅ 可覆盖 | ✅ 配置文件（`MINERU_DEFAULT_BACKEND`） | ✅ 正确 |
| **REST API** | ✅ 必填 | ✅ 可覆盖 | ❌ 硬编码 `"hybrid-http-client"` | ❌ 不一致 |

**结论**：
- ✅ Backend 可以通过请求构造（覆盖默认值）
- ⚠️ REST API 的默认值处理不一致（应修复）

---

## 6. 建议

**立即修复**：
1. ✅ 修改 REST API 的 backend 参数，从配置文件读取默认值
2. ✅ 确保 MCP Tools 和 REST API 的处理逻辑一致

**修复代码**：
```python
@app.post("/parse")
async def parse_pdf_sync(
    backend: Optional[str] = Form(default=None),  # ✅ 可选参数
    ...
):
    config = get_config()
    effective_backend = backend if backend is not None else config.default_backend
    validated_backend = validate_backend(effective_backend)
```

---

✌Bazinga！