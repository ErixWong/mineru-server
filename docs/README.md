# MinerU MCP+API 增强项目文档

**项目**: MinerU + MCP Server + REST API
**仓库**: https://github.com/ErixWong/MinerU
**更新时间**: 2026-05-09

---

## 文档结构

```
docs/
├── README.md                    # 本文档（索引）
├── mineru/                      # MinerU 原生文档
│   ├── config_flow.md           # MinerU 配置流程
│   ├── container_usage.md       # MinerU 容器使用
│   ├── llm_requirements.md      # LLM 需求说明
│   └── images/                  # 文档图片
├── mcp-server/                  # MCP Server 文档（待整理）
├── deployment/                  # 部署文档
│   └ strix-halo/                # Strix Halo 特定部署
├── design/                      # 设计文档
│   ├── drafts/                  # 设计草稿
│   │   └ mcp-api-enhancement-design.md  # ✅ 核心设计文档
│   └── completed/               # 已完成设计
├── tasks/                       # 任务记录
│   ├── active/                  # 进行中的任务
│   │   └ 方法清单-完整版.md      # ✅ 当前方法清单
│   └── archived/                # 已归档任务
│       ├── phase1-code-review.md
│       ├── phase2-test-report.md
│       ├── phase2.5-实现报告.md
│       └ backend参数确认.md
│       └ 查询结果端点确认.md
│       └ 其他评估文档...
└── archive/                     # 旧文档归档
    └ early-mcp-design/          # 早期 MCP 设计
    └ 其他归档文档...
```

---

## 快速开始

### 1. 核心设计文档

**必读文档**：
- `design/drafts/mcp-api-enhancement-design.md` - MCP+API 增强设计（完整版）
- `tasks/active/方法清单-完整版.md` - 当前可用方法清单

### 2. MinerU 原生文档

**MinerU 使用**：
- `mineru/config_flow.md` - MinerU 配置流程
- `mineru/container_usage.md` - MinerU 容器部署
- `mineru/llm_requirements.md` - LLM 模型需求

### 3. 部署文档

**特定部署**：
- `deployment/strix-halo/` - Strix Halo 特定部署方案

---

## 实施历程

### Phase 1: 代码重组（已完成 ✅）
- 文档：`tasks/archived/phase1-code-review.md`
- 内容：MinerU Git Submodule，MCP 代码移动

### Phase 2: 配置和测试（已完成 ✅）
- 文档：`tasks/archived/phase2-test-report.md`
- 内容：零安装启动，Proxy 模式测试

### Phase 2.5: 文件上传支持（已完成 ✅）
- 文档：`tasks/archived/phase2.5-实现报告.md`
- 内容：MCP base64 输入，REST API multipart 上传

---

## 当前可用功能

### MCP Tools（6 个）
- `parse_pdf(file_base64)` - 同步解析
- `submit_task(file_base64)` - 异步提交
- `get_task(task_id)` - 查询状态和结果
- `get_images(task_id)` - 获取图片
- `list_backends()` - 列出后端
- `health_check()` - 健康检查

### REST API（6 个核心）
- `POST /api/parse` - 同步解析（multipart 上传）
- `POST /api/tasks` - 异步提交（multipart 上传）
- `GET /api/tasks/{id}` - 查询状态和结果
- `GET /api/tasks/{id}/images` - 获取图片
- `GET /api/backends` - 列出后端
- `GET /api/health` - 健康检查

### MinerU Native API（Proxy）
- `/mineru_api/file_parse` - MinerU 原生同步解析
- `/mineru_api/tasks` - MinerU 原生异步提交
- `/mineru_api/tasks/{id}` - MinerU 原生状态查询
- `/mineru_api/tasks/{id}/result` - MinerU 原生结果（ZIP）

---

## 快速启动

### 启动 MCP Server（Proxy 模式）

```bash
# 克隆仓库
git clone https://github.com/ErixWong/MinerU.git
cd MinerU

# 启动 MCP Server + MinerU Native API
python start-mcp-server.py --mode http --port 8001 --enable-mineru-api
```

### 访问服务

- **MCP Tools**: http://localhost:8001/mcp
- **REST API**: http://localhost:8001/api
- **MinerU Native**: http://localhost:8001/mineru_api
- **API Docs**: http://localhost:8001/api/docs

---

## 详细文档索引

### 设计文档

| 文档 | 内容 | 状态 |
|------|------|------|
| `design/drafts/mcp-api-enhancement-design.md` | MCP+API 增强完整设计 | ✅ 当前有效 |

### 功能文档

| 文档 | 内容 | 状态 |
|------|------|------|
| `tasks/active/方法清单-完整版.md` | MCP/API/MinerU Native 方法清单 | ✅ 当前有效 |

### 任务归档

| 文档 | 内容 | 状态 |
|------|------|------|
| `tasks/archived/phase1-code-review.md` | Phase 1 代码审查报告 | ✅ 已完成 |
| `tasks/archived/phase2-test-report.md` | Phase 2 测试报告 | ✅ 已完成 |
| `tasks/archived/phase2.5-实现报告.md` | Phase 2.5 文件上传实现 | ✅ 已完成 |
| `tasks/archived/backend参数确认.md` | Backend 参数处理逻辑 | ✅ 设计完成 |
| `tasks/archived/查询结果端点确认.md` | 查询结果端点设计 | ✅ 设计完成 |

### MinerU 原生文档

| 文档 | 内容 |
|------|------|
| `mineru/config_flow.md` | MinerU 配置流程说明 |
| `mineru/container_usage.md` | MinerU 容器部署使用 |
| `mineru/llm_requirements.md` | LLM 模型需求配置 |

### 部署文档

| 文档 | 内容 |
|------|------|
| `deployment/strix-halo/deployment.md` | Strix Halo 部署方案 |
| `deployment/strix-halo/compose-scheme-a.yml` | 部署方案 A |
| `deployment/strix-halo/compose-scheme-b.yml` | 部署方案 B |

---

## 归档文档

**位置**: `docs/archive/`

**说明**: 旧文档、早期设计、已过时文档已归档，仅供参考。

---

## 项目架构

```
MinerU MCP+API 增强项目

├── MinerU 原生功能（src/mineru/）
│   ├── PDF 解析核心
│   ├── 多种后端
│   └── VLM 支持
│
├── MCP Server（mcp-server/）
│   ├── MCP Tools（base64 输入）
│   ├── REST API（multipart 上传）
│   └── MinerU Native API Proxy
│
└── Docker 部署
    ├── All-in-One 模式
    ├── Separated 模式
    └ 特定部署方案
```

---

## 联系和贡献

- **仓库**: https://github.com/ErixWong/MinerU
- **Issues**: https://github.com/ErixWong/MinerU/issues
- **原始 MinerU**: https://github.com/opendatalab/MinerU

---

✌Bazinga！