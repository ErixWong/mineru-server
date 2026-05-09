# Docker 部署说明（新架构 - 单进程）

**架构更新**: 已更新为**单进程 Proxy 模式**，所有服务在一个进程中运行。

---

## 🎯 新架构特点

### 单进程，三服务路由

```
单进程（uvicorn，端口 8001）
│
├── /mcp          → MCP Tools（MCP 协议）
├── /api          → REST API（HTTP）
└── /mineru_api   → MinerU Native API（Proxy）
```

**优势**：
- ✅ 单进程，单端口（8001）
- ✅ 启动简单（无启动脚本）
- ✅ 高效调用（MinerU 内嵌）
- ✅ 容器管理简单（单进程）

---

## 📦 部署模式

### 模式一：All-in-One（单进程，推荐 ✅）

**特点**：MCP + API + MinerU Native 在一个进程

**文件**：
- `Dockerfile.all-in-one` - All-in-One 镜像
- `docker-compose.yml` - All-in-One 编排

**快速启动**：
```bash
# 1. 配置环境变量
cp ../.env.example ../.env
vim ../.env

# 2. 构建并启动
docker-compose -f docker-compose.yml up -d

# 3. 查看日志
docker logs mineru-mcp-all-in-one

# 4. 访问服务（单端口 8001）
# MCP Tools:        http://localhost:8001/mcp
# REST API:         http://localhost:8001/api
# MinerU Native:    http://localhost:8001/mineru_api
# API Docs:         http://localhost:8001/api/docs
```

---

### 模式二：Separated（分离模式，可选）

**特点**：MinerU 和 MCP Server 分离部署

**文件**：
- `Dockerfile.mcp-only` - MCP Server 独立镜像
- `docker-compose.separated.yml` - 分离模式编排

**快速启动**：
```bash
# 构建并启动
docker-compose -f docker-compose.separated.yml up -d

# 服务访问：
# MinerU FastAPI:   http://localhost:8000
# MCP Server:       http://localhost:8001
```

---

## 🔧 环境变量配置

创建 `.env` 文件（参考 `.env.example`）：

```bash
# MinerU VLM 配置
MINERU_VLM_BASE_URL=http://vlm-server:30000/v1
MINERU_VLM_API_KEY=your-api-key
MINERU_VLM_MODEL=your-model-name

# MinerU 默认后端
MINERU_DEFAULT_BACKEND=hybrid-http-client

# MCP Server 配置
MCP_LOG_LEVEL=INFO
MCP_HTTP_AUTH_TOKEN=your-secret-token

# CORS 配置
MINERU_CORS_ORIGINS=*
```

---

## 📋 常用命令

**构建镜像**：
```bash
docker-compose -f docker-compose.yml build
```

**启动服务**：
```bash
docker-compose -f docker-compose.yml up -d
```

**停止服务**：
```bash
docker-compose -f docker-compose.yml down
```

**查看日志**：
```bash
docker logs mineru-mcp-all-in-one
```

**重启服务**：
```bash
docker-compose -f docker-compose.yml restart
```

---

## 🎯 端口说明

| 模式 | 端口 | 服务 |
|------|------|------|
| **All-in-One** | 8001 | MCP + API + MinerU Native（单进程） |
| **Separated** | 8000 | MinerU FastAPI（独立进程） |
| **Separated** | 8001 | MCP Server（独立进程） |

---

## 🏗️ 架构对比

### 新架构（单进程，推荐 ✅）

**启动方式**：
```bash
mineru-mcp --enable-mineru-api --port 8001
```

**架构**：
```
单进程（uvicorn）
│
├── /mcp          → MCP Tools
├── /api          → REST API
└── /mineru_api   → MinerU Native API（内嵌）
```

**优势**：
- ✅ 单进程，简单管理
- ✅ 单端口，简单访问
- ✅ 无启动脚本，直接启动

---

### 旧架构（双进程，已废弃）

**启动方式**：
```bash
# 需启动脚本管理两个进程
/app/start.sh

# 启动脚本内容：
uvicorn mineru.cli.fast_api:app --port 8000 &  # 进程 1
mineru-mcp --port 8001 &                        # 进程 2
wait
```

**架构**：
```
进程 1（MinerU FastAPI，端口 8000）
进程 2（MCP Server，端口 8001） → HTTP 调用 → 进程 1
```

**劣势**：
- ⚠️ 双进程，管理复杂
- ⚠️ 双端口，访问复杂
- ⚠️ 需启动脚本，维护复杂

---

## 🐛 故障排查

**问题 1: MCP Server 无法启动**
```bash
# 检查日志
docker logs mineru-mcp-all-in-one

# 检查健康状态
curl http://localhost:8001/health
```

**问题 2: MinerU Native API 无法访问**
```bash
# 检查 MinerU Native API
curl http://localhost:8001/mineru_api/health

# 检查 MinerU Native Docs
curl http://localhost:8001/mineru_api/docs
```

**问题 3: VLM 配置错误**
```bash
# 检查环境变量
docker exec mineru-mcp-all-in-one env | grep VLM
```

---

## 📚 相关文档

- [项目设计文档](../docs/design/drafts/mcp-api-enhancement-design.md)
- [MCP Server 使用文档](../mcp-server/README.md)
- [MinerU 官方文档](https://mineru.readthedocs.io/)
- [新架构说明](../docs/tasks/active/方法清单-完整版.md)

---

## 🔄 从旧架构迁移

**迁移步骤**：

1. **停止旧容器**：
```bash
docker-compose down
```

2. **拉取新代码**：
```bash
git pull
```

3. **重新构建**：
```bash
docker-compose build
```

4. **启动新容器**：
```bash
docker-compose up -d
```

5. **验证服务**：
```bash
curl http://localhost:8001/health
```

---

**新架构已更新完成！单进程启动所有服务！**