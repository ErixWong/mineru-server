# Docker 部署说明

本目录包含 MinerU MCP Server 的 Docker 配置文件，支持两种部署模式。

---

## 📦 部署模式

### 模式一：All-in-One（推荐 ✅）

**特点**: MinerU + MCP Server 在同一容器

**适用场景**: 个人使用、测试开发、单机部署

**文件**:
- `Dockerfile.all-in-one` - All-in-One 镜像
- `docker-compose.yml` - All-in-One 编排

**快速启动**:
```bash
# 1. 配置环境变量
cp ../.env.example ../.env
vim ../.env

# 2. 构建并启动
docker-compose -f docker-compose.yml up -d

# 3. 查看日志
docker logs mineru-mcp-all-in-one

# 4. 访问服务
# MinerU FastAPI: http://localhost:8000
# MCP Server:     http://localhost:8001
```

---

### 模式二：分离部署（可选）

**特点**: MinerU 和 MCP Server 分别部署

**适用场景**: 生产环境、多实例部署、独立升级

**文件**:
- `Dockerfile.mcp-only` - MCP Server 独立镜像
- `docker-compose.separated.yml` - 分离模式编排

**快速启动**:
```bash
# 1. 配置环境变量
cp ../.env.example ../.env
vim ../.env

# 2. 构建并启动
docker-compose -f docker-compose.separated.yml up -d

# 3. 查看日志
docker logs mineru-api        # MinerU 日志
docker logs mineru-mcp-server # MCP Server 日志

# 4. 访问服务
# MinerU FastAPI: http://localhost:8000
# MCP Server:     http://localhost:8001
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
MCP_HTTP_AUTH_TOKEN=your-auth-token

# CORS 配置
MINERU_CORS_ORIGINS=*
```

---

## 📋 常用命令

**构建镜像**:
```bash
docker-compose -f docker-compose.yml build
docker-compose -f docker-compose.separated.yml build
```

**启动服务**:
```bash
docker-compose -f docker-compose.yml up -d
docker-compose -f docker-compose.separated.yml up -d
```

**停止服务**:
```bash
docker-compose -f docker-compose.yml down
docker-compose -f docker-compose.separated.yml down
```

**查看日志**:
```bash
docker logs mineru-mcp-all-in-one       # All-in-One
docker logs mineru-api                  # 分离模式 - MinerU
docker logs mineru-mcp-server           # 分离模式 - MCP Server
```

**重启服务**:
```bash
docker-compose -f docker-compose.yml restart
docker-compose -f docker-compose.separated.yml restart
```

---

## 🎯 端口说明

| 模式 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| All-in-One | mineru-mcp-all-in-one | 8000 | MinerU FastAPI |
| All-in-One | mineru-mcp-all-in-one | 8001 | MCP Server |
| 分离模式 | mineru-api | 8000 | MinerU FastAPI |
| 分离模式 | mineru-mcp-server | 8001 | MCP Server |

---

## 🐛 故障排查

**问题 1: MinerU 无法启动**
```bash
# 检查 GPU 支持
docker logs mineru-mcp-all-in-one | grep "GPU"

# 检查 VLM 配置
docker logs mineru-mcp-all-in-one | grep "VLM"
```

**问题 2: MCP Server 无法连接 MinerU**
```bash
# 检查 MinerU 健康状态
curl http://localhost:8000/health

# 检查 MCP Server 配置
docker logs mineru-mcp-server | grep "MINERU_API_BASE"
```

**问题 3: 认证失败**
```bash
# 检查 AUTH_TOKEN 配置
docker logs mineru-mcp-server | grep "AUTH_TOKEN"

# 测试认证
curl -H "Authorization: Bearer your-token" http://localhost:8001/api/health
```

---

## 📚 相关文档

- [项目设计文档](../docs/design/drafts/mcp-api-enhancement-design.md)
- [MCP Server 使用文档](../mcp-server/README.md)
- [MinerU 官方文档](https://mineru.readthedocs.io/)