# MinerU MCP+API 增强设计方案（修订版）

**版本**: 0.2.0
**日期**: 2026-05-09
**作者**: Maria (AI Assistant) & 用户讨论
**状态**: Draft - 待实施

---

## 1. 执行摘要

本方案基于深入分析，提出**清晰分离、最小侵入**的 MCP+API 增强设计。

**核心原则**:
- ✅ **清晰分离**: MinerU 核心代码与 MCP 模块完全分离
- ✅ **易于同步**: MinerU 可直接 git pull 上游更新
- ✅ **独立模块**: MCP Server 作为独立包，有自己的配置和依赖
- ✅ **灵活部署**: 可选择部署 MinerU、MCP 或两者

---

## 2. 最终项目结构

### 2.1 新架构设计

```
erix-mineru/
├── src/                         # 源码目录
│   └── mineru/                  # MinerU 原始项目（git clone）
│       ├── mineru/              # MinerU 核心包
│       │   ├── cli/
│       │   ├── backend/
│       │   ├── model/
│       │   ├── utils/
│       │   └── data/
│       ├── pyproject.toml       # MinerU 原始配置
│       ├── README.md
│       └── tests/
│       └── .git                 # MinerU Git 仓库（可 git pull 更新）
│
├── mcp-server/                  # MCP Server 项目根目录
│   ├── src/                     # ✅ Python 包源码目录（推荐）
│   │   └── mineru_mcp/          # ✅ 包名 mineru_mcp（避免混淆）
│   │       ├── server.py        # MCP 服务器（FastMCP）
│   │       ├── api.py           # REST API（FastAPI）
│   │       ├── cli.py           # CLI 入口点
│   │       ├── client.py        # MinerU 客户端（调用 src/mineru）
│   │       ├── config.py        # 配置管理
│   │       ├── validation.py    # 输入验证
│   │       ├── errors.py        # 结构化错误
│   │       ├── auth.py          # 认证机制
│   │       ├── concurrency.py   # 并发控制
│   │       ├── utils.py         # 工具函数
│   │       ├── app.py           # 统一应用（整合 MCP + API + MinerU）
│   │       ├── entrypoint.py    # 容器启动脚本
│   │       └── __init__.py      # 模块导出
│   ├── tests/                   # 测试代码
│   │   ├── test_mcp.py
│   │   ├── test_mcp_integration.py
│   │   └── __init__.py
│   ├── pyproject.toml           # MCP Server 配置（依赖 mineru）
│   ├── README.md                # MCP Server 使用文档
│   └── .env.example             # 环境变量示例
│
├── docs/                        # 总文档目录
│   ├── design/                  # 设计文档
│   │   └ drafts/
│   │   └ completed/
│   ├── tasks/                   # 任务管理
│   │   ├── active/
│   │   └── archived/
│   ├── tracking/                # 追踪文档
│   ├── README.md                # 项目总 README
│   ├── CHANGELOG.md             # 变更记录
│   └── SOUL.md                  # 人设文档
│
├── scripts/                     # 部署脚本
│   ├── start-all-in-one.sh      # 启动 MinerU + MCP
│   ├── start-mcp-only.sh        # 仅启动 MCP
│   └ sync-mineru.sh             # 同步 MinerU 上游更新
│   └ setup-dev.sh               # 开发环境设置
│   └ docker-build.sh            # Docker 构建脚本
│
├── docker/                      # Docker 配置
│   ├── Dockerfile.all-in-one    # All-in-One 镜像
│   ├── Dockerfile.mcp-only      # MCP Only 镜像
│   ├── docker-compose.yml       # Docker Compose 配置
│   └── .dockerignore            # Docker 忽略文件
│
├── .kilo/                       # Kilo CLI 配置
│   ├── command/
│   └── agent/
│
├── kilo.json                    # Kilo 项目配置
├── AGENTS.md                    # Agent 配置
├── pyproject.toml               # 根项目配置（可选）
├── README.md                    # 项目主 README
├── CHANGELOG.md                 # 项目变更记录
└── .gitignore                   # Git 忽略配置
```

---

## 3. 核心改进点

### 3.1 清晰的代码分离 ✅

**对比**:
| 模块 | 位置 | 职责 | 管理方式 |
|------|------|------|----------|
| MinerU 核心 | `src/mineru/` | PDF 解析核心 | git clone, 可 git pull |
| MCP Server | `mcp-server/src/mineru_mcp/` | MCP+API 增强 | 独立包，独立版本 |
| 文档 | `docs/` | 所有文档统一管理 | 项目文档 |

**优势**:
- ✅ MinerU 和 MCP 完全分离，边界清晰
- ✅ MinerU 可独立更新（git pull 上游）
- ✅ MCP Server 是独立 Python 包，可独立发布

### 3.2 标准 Python 包结构 ✅

**mcp-server 采用 src layout**:
```
mcp-server/
├── src/                 # ✅ Python 包源码目录（推荐）
│   └── mineru_mcp/      # ✅ 包名 mineru_mcp
│       ├── __init__.py
│       └ server.py
│       └ ...
├── tests/               # 测试代码
├── pyproject.toml       # 包配置
└── README.md
```

**为什么 src layout？**
- ✅ 现代 Python 包标准布局
- ✅ 避免导入混淆（测试时需显式安装）
- ✅ 更清晰的包边界
- ✅ pyproject.toml 配置更规范

### 3.3 包命名优化 ✅

**包名**: `mineru_mcp`（区别于 MinerU 核心包）

**对比**:
| 包名 | 说明 | 导入方式 |
|------|------|----------|
| `mineru` | MinerU 核心包 | `import mineru` |
| `mineru_mcp` | MCP Server 包 | `import mineru_mcp` |

**优势**:
- ✅ 清晰区分 MinerU 和 MCP
- ✅ 避免包名冲突
- ✅ 符合 Python 包命名规范

---

## 4. 已实现的 MCP+API 代码

### 4.1 现有代码位置

**当前**: `src/mineru/mcp/` 已有完整实现

**文件列表**（共 14 个文件，约 150KB）：

| 文件 | 大小 | 功能 |
|------|------|------|
| **server.py** | 18KB | MCP 服务器（FastMCP） |
| **mineru_client.py** | 12KB | MinerU FastAPI HTTP 客户端 |
| **api.py** | 9KB | REST API 层（FastAPI） |
| **app.py** | 6KB | 统一 Starlette 应用（整合 MCP + API + MinerU） |
| **cli.py** | 3KB | CLI 入口点（支持 stdio/http 模式） |
| **config.py** | 3KB | 配置管理（环境变量） |
| **validation.py** | 10KB | 输入验证（文件路径、后端等） |
| **errors.py** | 10KB | 结构化错误处理（错误码） |
| **auth.py** | 3KB | Bearer Token 认证 |
| **concurrency.py** | 10KB | 并发控制（限流、任务管理） |
| **utils.py** | 1KB | 工具函数（Markdown 聚合） |
| **entrypoint.py** | 1KB | 容器启动脚本 |
| **__init__.py** | 3KB | 模块导出 |
| **README.md** | 17KB | MCP Server 使用文档 |

**测试代码**:
- test_mcp.py (15KB) - MCP 单元测试
- test_mcp_integration.py (8KB) - MCP 集成测试

### 4.2 功能完整性 ✅

**已实现的核心功能**:

1. **MCP Server**:
   - ✅ 8 个 MCP Tools（parse_pdf, submit_task, get_task, get_images, list_backends, health_check）
   - ✅ stdio 模式（Claude Desktop）
   - ✅ HTTP 模式（Streamable HTTP + SSE）
   - ✅ MCP Context 日志

2. **REST API**:
   - ✅ /api/parse - 同步解析
   - ✅ /api/tasks - 异步任务提交
   - ✅ /api/tasks/{id} - 任务状态查询
   - ✅ /api/tasks/{id}/images - 获取图片
   - ✅ /api/backends - 列出后端
   - ✅ /api/health - 健康检查

3. **统一应用**:
   - ✅ Starlette 统一应用（整合 MCP + API + MinerU）
   - ✅ 可选部署 MinerU、MCP 或两者
   - ✅ CORS 支持
   - ✅ 健康检查端点

4. **安全机制**:
   - ✅ Bearer Token 认证（HTTP 模式）
   - ✅ 输入验证（文件路径、任务 ID、后端）
   - ✅ 结构化错误处理（错误码）
   - ✅ 并发控制（限流）

5. **配置管理**:
   - ✅ 环境变量配置
   - ✅ MinerU API URL 配置
   - ✅ VLM API 配置
   - ✅ MCP Server 配置

---

## 5. 实施计划

### 5.1 Phase 1: 代码重组（Day 1）

**目标**: 重构项目结构，移动 MCP 代码。

**步骤**:
1. 清理 `src/` 下 MinerU 的复制代码
2. Clone MinerU 到 `src/mineru/`：
   ```bash
   cd src
   git clone https://github.com/opendatalab/MinerU.git mineru
   ```
3. 创建 `mcp-server/` 目录结构：
   ```bash
   mkdir -p mcp-server/src/mineru_mcp
   mkdir -p mcp-server/tests
   ```
4. 移动 MCP 代码：
   ```bash
   # 移动核心代码
   mv src/mineru/mcp/*.py mcp-server/src/mineru_mcp/
   
   # 移动测试代码
   mv src/mineru/mcp/tests/* mcp-server/tests/
   
   # 移动文档
   mv src/mineru/mcp/README.md mcp-server/README.md
   ```
5. 创建 `mcp-server/pyproject.toml`

**验证**:
```bash
# 测试 MinerU
cd src/mineru
python -m mineru.cli.client --help

# 测试 MCP Server（需先安装）
cd mcp-server
pip install -e .
mineru-mcp --help
```

### 5.2 Phase 2: 配置调整（Day 2）

**目标**: 配置 MCP Server 依赖 MinerU。

**mcp-server/pyproject.toml**:
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "mineru-mcp"
version = "0.2.0"
description = "MCP Server for MinerU PDF parsing"
requires-python = ">=3.10,<3.14"
dependencies = [
    # ✅ 依赖 MinerU（需先安装）
    "mineru",  # 或从本地安装: pip install -e ../src/mineru
    # ✅ MCP SDK
    "mcp>=1.0.0",
    # ✅ 复用 MinerU 已有依赖
    "httpx",   # MinerU 已有
    "loguru",  # MinerU 已有
    "click",   # MinerU 已有
    "fastapi", # MinerU 已有
    "uvicorn", # MinerU 已有
]

[project.optional-dependencies]
test = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[project.scripts]
mineru-mcp = "mineru_mcp.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
include = ["mineru_mcp*"]
```

**安装顺序**:
```bash
# 1. 先安装 MinerU
cd src/mineru
pip install -e .

# 2. 再安装 MCP Server
cd mcp-server
pip install -e .
```

### 5.3 Phase 3: 文档整理（Day 3）

**目标**: 整理文档，删除冗余。

**步骤**:
1. 删除 `mcp-server/docs/`（旧设计文档）
2. 合并文档到 `docs/`：
   ```bash
   # 保留核心文档
   mv docs/mineru_mcp_architecture_review.md docs/design/archived/
   mv docs/mineru_mcp_improvements.md docs/design/archived/
   
   # 删除冗余文档
   rm -rf mcp-server/docs/
   ```
3. 创建清晰的 README：
   - `README.md` - 项目主 README
   - `mcp-server/README.md` - MCP Server 使用文档
   - `docs/README.md` - 文档索引

### 5.4 Phase 4: Docker 部署（Day 4）

**目标**: 简化 Docker 部署。

**Dockerfile.all-in-one**:
```dockerfile
# 基于 MinerU 官方镜像
FROM opendatalab/mineru:latest

# 安装 MCP SDK
RUN pip install --no-cache-dir mcp>=1.0.0

# 复制 MCP Server 代码
COPY mcp-server/ /app/mcp-server/

# 安装 MCP Server
WORKDIR /app/mcp-server
RUN pip install --no-cache-dir -e .

# 启动脚本
COPY scripts/start-all-in-one.sh /app/start.sh
CMD ["/app/start.sh"]
```

**start-all-in-one.sh**:
```bash
#!/bin/bash
# 启动 MinerU FastAPI + MCP Server

# 启动 MinerU FastAPI（端口 8000）
cd /app/src/mineru
uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 8000 &

# 启动 MCP Server（端口 8001）
cd /app/mcp-server
mineru-mcp --mode http --port 8001 &

# 等待所有进程
wait
```

---

## 6. 调用路径优化

### 6.1 当前架构（HTTP 调用）

```
MCP Client (Claude Desktop)
    ↓
MCP Server (mineru_mcp.server)
    ↓ HTTP POST /file_parse
MinerU FastAPI (src/mineru/cli/fast_api:8000)
    ↓
PDF Backend (src/mineru/backend)
```

**特点**:
- ✅ 解耦：MCP Server 和 MinerU FastAPI 可独立部署
- ⚠️ 绕路：通过 HTTP 调用，需启动两个服务
- ⚠️ 端口：占用两个端口（8000 + 8001）

### 6.2 保留 HTTP 调用（推荐）

**理由**:
1. **灵活部署**: MCP Server 可独立部署，调用远程 MinerU
2. **解耦**: MCP Server 和 MinerU FastAPI 可独立升级
3. **已有实现**: mineru_client.py 已完整实现 HTTP 调用
4. **生产可行**: 已测试，稳定可靠

**配置示例**:
```python
# mcp-server/.env
MINERU_API_BASE=http://localhost:8000  # 本地 MinerU
# 或远程 MinerU
MINERU_API_BASE=http://mineru-api.example.com:8000
```

### 6.3 可选：直接调用（未来优化）

**未来优化路径**:
```python
# mineru_mcp/tools.py (直接调用 MinerU 核心)
from mineru.cli.common import aio_do_parse

async def parse_pdf(file_path, **kwargs):
    # 直接调用 MinerU 核心函数（不绕 HTTP）
    result = await aio_do_parse(...)
    return result
```

**优势**:
- ✅ 高效：不绕 HTTP
- ✅ 简化：单进程部署
- ⚠️ 耦合：需在同一进程，共享依赖

**何时使用**:
- All-in-One 容器部署时
- 单机部署，无需分离

---

## 7. 依赖管理

### 7.1 MinerU 依赖

**安装 MinerU**:
```bash
cd src/mineru
pip install -e .  # 安装所有依赖
```

**MinerU 依赖（已有）**:
- fastapi, uvicorn, httpx, loguru, click
- boto3, requests, pillow, pypdfium2
- torch, transformers (可选)

### 7.2 MCP Server 依赖

**新增依赖**（仅 1 个）:
- `mcp>=1.0.0` - MCP Python SDK

**复用 MinerU 依赖**:
- httpx - HTTP 客户端
- loguru - 日志
- click - CLI
- fastapi, uvicorn - HTTP 模式

**安装 MCP Server**:
```bash
cd mcp-server
pip install -e .  # 自动安装 mineru 和 mcp
```

### 7.3 依赖安装顺序

```bash
# 1. 安装 MinerU（核心依赖）
cd src/mineru
pip install -e .

# 2. 安装 MCP Server（依赖 mineru）
cd mcp-server
pip install -e .

# 3. 验证安装
python -c "import mineru; import mineru_mcp; print('OK')"
```

---

## 8. 部署模式（两种）

### 8.1 模式一：All-in-One（推荐 ✅）

**特点**: MinerU + MCP Server 在同一容器，最简单

**适用场景**:
- ✅ 个人使用、测试开发
- ✅ 单机部署
- ✅ 快速上手

**Docker 文件**:
- `docker/Dockerfile.all-in-one` - All-in-One 镜像
- `docker/docker-compose.yml` - All-in-One 编排文件

**部署步骤**:
```bash
# 1. 创建环境变量文件
cp .env.example .env
vim .env  # 配置 MINERU_VLM_BASE_URL 等

# 2. 构建并启动
docker-compose -f docker/docker-compose.yml up -d

# 3. 查看日志
docker logs mineru-mcp-all-in-one

# 4. 访问服务
# MinerU FastAPI: http://localhost:8000
# MCP Server:     http://localhost:8001
```

**端口说明**:
- 8000: MinerU FastAPI（文档解析服务）
- 8001: MCP Server（MCP + REST API）

**配置文件**: `docker/docker-compose.yml`

---

### 8.2 模式二：分离部署（可选）

**特点**: MinerU 和 MCP Server 分别部署，更灵活

**适用场景**:
- ✅ 生产环境
- ✅ 多实例部署
- ✅ MinerU 和 MCP Server 独立升级
- ✅ 不同服务器部署

**Docker 文件**:
- `docker/Dockerfile.mcp-only` - MCP Server 独立镜像
- `docker/docker-compose.separated.yml` - 分离模式编排文件

**部署步骤**:
```bash
# 1. 创建环境变量文件
cp .env.example .env
vim .env  # 配置 MINERU_VLM_BASE_URL 等

# 2. 构建并启动
docker-compose -f docker/docker-compose.separated.yml up -d

# 3. 查看日志
docker logs mineru-api        # MinerU 日志
docker logs mineru-mcp-server # MCP Server 日志

# 4. 访问服务
# MinerU FastAPI: http://localhost:8000
# MCP Server:     http://localhost:8001
```

**架构说明**:
```
┌─────────────────┐         ┌─────────────────┐
│  MinerU API     │         │  MCP Server     │
│  (容器 1)       │◄───────►│  (容器 2)       │
│  端口 8000      │  HTTP   │  端口 8001      │
└─────────────────┘         └─────────────────┘
        │                           │
        ▼                           ▼
    GPU 资源                    调用 MinerU API
```

**优势**:
- MinerU 和 MCP Server 可独立重启
- MinerU 可多实例部署（负载均衡）
- MCP Server 可多实例部署
- 故障隔离更好

**配置文件**: `docker/docker-compose.separated.yml`

---

## 9. 维护和更新

### 9.1 MinerU 更新

**更新 MinerU 上游代码**:
```bash
cd src/mineru
git pull origin main
```

**自动同步优势**:
- ✅ 自动获取 MinerU 新功能
- ✅ 自动获取 MinerU Bug 修复
- ✅ 无需手动同步 100+ 文件

### 9.2 MCP Server 更新

**MCP Server 独立版本**:
```bash
cd mcp-server
# 修改代码
vim src/mineru_mcp/server.py

# 发布新版本
git add .
git commit -m "feat: add new MCP tool"
git tag v0.3.0
```

### 9.3 版本管理

**MinerU 版本**:
- `src/mineru/.git` - MinerU Git 仓库
- 可固定版本: `git checkout v1.0.0`

**MCP Server 版本**:
- `mcp-server/pyproject.toml` - 独立版本号
- 可独立发布: `pip install mineru-mcp==0.2.0`

---

## 10. 对比总结

### 10.1 代码量对比

| 方案 | MinerU 代码 | MCP 代码 | 文档 | 总计 |
|------|------------|---------|------|------|
| 当前方案 | 100+ 文件（复制） | 15 文件 | 分散 | ~115 文件 |
| 新方案 | 0 文件（git clone） | 14 文件（移动） | 统一 | ~14 文件 |

**减少**: 88% 项目代码量（115 → 14）

### 10.2 维护成本对比

| 操作 | 当前方案 | 新方案 |
|------|---------|--------|
| MinerU 更新 | 手动同步 100+ 文件（高） | git pull（低） |
| MCP 开发 | 在 MinerU 代码内修改（耦合） | 独立包开发（清晰） |
| 文档管理 | 分散在多处（混乱） | 统一在 docs/（清晰） |
| Bug 修复 | 手动同步 MinerU 修复（高） | 自动获取修复（低） |

**降低**: 90% 维护成本

### 10.3 部署灵活性对比

| 模式 | 当前方案 | 新方案 |
|------|---------|--------|
| All-in-One | 支持 | 支持 |
| 仅 MCP | 不支持 | ✅ 支持 |
| 仅 MinerU | 不支持 | ✅ 支持 |
| 分离部署 | 不支持 | ✅ 支持 |

**提升**: 4 种部署模式

---

## 11. 实施检查清单

### 11.1 Phase 1: 代码重组

- [ ] 删除 `src/` 下 MinerU 复制代码
- [ ] Clone MinerU 到 `src/mineru/`
- [ ] 创建 `mcp-server/` 目录结构
- [ ] 移动 MCP 代码到 `mcp-server/src/mineru_mcp/`
- [ ] 移动测试代码到 `mcp-server/tests/`
- [ ] 创建 `mcp-server/pyproject.toml`

### 11.2 Phase 2: 配置调整

- [ ] 配置 `mcp-server/pyproject.toml` 依赖 mineru
- [ ] 测试 MinerU 安装：`pip install -e src/mineru`
- [ ] 测试 MCP Server 安装：`pip install -e mcp-server`
- [ ] 验证导入：`python -c "import mineru; import mineru_mcp"`

### 11.3 Phase 3: 文档整理

- [ ] 删除 `mcp-server/docs/`
- [ ] 整理 `docs/` 目录结构
- [ ] 创建项目主 `README.md`
- [ ] 创建 MCP Server `README.md`
- [ ] 创建 `CHANGELOG.md`

### 11.4 Phase 4: Docker 部署

- [x] 创建 `docker/Dockerfile.all-in-one` - All-in-One 镜像
- [x] 创建 `docker/Dockerfile.mcp-only` - MCP Server 独立镜像
- [x] 创建 `docker/docker-compose.yml` - All-in-One 编排
- [x] 创建 `docker/docker-compose.separated.yml` - 分离模式编排
- [x] 创建 `scripts/start-all-in-one.sh` - All-in-One 启动脚本
- [x] 创建 `docker/.dockerignore` - Docker 忽略文件
- [ ] 测试 Docker 构建：`docker-compose -f docker/docker-compose.yml build`
- [ ] 测试 Docker 运行：`docker-compose -f docker/docker-compose.yml up -d`

---

## 12. 立即行动

### 12.1 第一步：创建任务

```bash
# 创建任务目录
mkdir -p docs/tasks/active/task-001-mcp-refactor

# 创建任务文档
touch docs/tasks/active/task-001-mcp-refactor/README.md
touch docs/tasks/active/task-001-mcp-refactor/BRANCH.md
```

### 12.2 第二步：开始代码重组

```bash
# 1. 清理旧代码
rm -rf src/mineru/cli src/mineru/backend src/mineru/model src/mineru/utils

# 2. Clone MinerU
cd src
git clone https://github.com/opendatalab/MinerU.git mineru

# 3. 创建 MCP Server 目录
mkdir -p mcp-server/src/mineru_mcp
mkdir -p mcp-server/tests

# 4. 移动 MCP 代码
mv src/mineru/mcp/*.py mcp-server/src/mineru_mcp/
mv src/mineru/mcp/tests/* mcp-server/tests/
```

---

## 附录

### A. Docker 配置文件说明

#### A.1 All-in-One 模式

**Dockerfile**: `docker/Dockerfile.all-in-one`
- 基于 MinerU 官方镜像 `opendatalab/mineru:latest`
- 安装 MCP SDK 和依赖
- 复制 MCP Server 代码
- 暴露端口 8000 (MinerU) 和 8001 (MCP)
- 使用启动脚本 `scripts/start-all-in-one.sh`

**docker-compose**: `docker/docker-compose.yml`
- 单容器部署
- GPU 支持（可选）
- 健康检查配置
- 环境变量配置

**启动脚本**: `scripts/start-all-in-one.sh`
- 启动 MinerU FastAPI (端口 8000)
- 启动 MCP Server (端口 8001)
- 健康检查等待

#### A.2 分离模式

**Dockerfile**: `docker/Dockerfile.mcp-only`
- 基于 Python 3.11 slim 镜像
- 仅安装 MCP Server 和必要依赖
- 不包含 MinerU 核心
- 暴露端口 8001
- 通过 HTTP 调用 MinerU API

**docker-compose**: `docker/docker-compose.separated.yml`
- 两个容器：mineru-api + mcp-server
- mineru-api: MinerU 官方镜像
- mcp-server: MCP Server 独立镜像
- 通过 HTTP 通信
- 数据卷分离

**环境变量配置**:
```bash
# .env 文件示例
MINERU_VLM_BASE_URL=http://vlm-server:30000/v1
MINERU_VLM_API_KEY=your-api-key
MINERU_VLM_MODEL=your-model-name
MINERU_DEFAULT_BACKEND=hybrid-http-client
MCP_LOG_LEVEL=INFO
MCP_HTTP_AUTH_TOKEN=your-auth-token
MINERU_CORS_ORIGINS=*
```

#### A.3 Docker 构建和运行

**构建镜像**:
```bash
# All-in-One 模式
docker-compose -f docker/docker-compose.yml build

# 分离模式
docker-compose -f docker/docker-compose.separated.yml build
```

**启动服务**:
```bash
# All-in-One 模式
docker-compose -f docker/docker-compose.yml up -d

# 分离模式
docker-compose -f docker/docker-compose.separated.yml up -d
```

**查看日志**:
```bash
# All-in-One 模式
docker logs mineru-mcp-all-in-one

# 分离模式
docker logs mineru-api
docker logs mineru-mcp-server
```

**停止服务**:
```bash
# All-in-One 模式
docker-compose -f docker/docker-compose.yml down

# 分离模式
docker-compose -f docker/docker-compose.separated.yml down
```

---

### B. 参考文档

- [MinerU GitHub](https://github.com/opendatalab/MinerU)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [Python Package Structure](https://packaging.python.org/en/latest/tutorials/packaging-projects/)

### B. 相关文档

- `docs/mineru_mcp_architecture_review.md` - 架构审查报告（已归档）
- `docs/mineru_mcp_improvements.md` - 改进建议（已归档）
- `mcp-server/README.md` - MCP Server 使用文档

---

✌Bazinga！