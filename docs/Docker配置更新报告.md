# Docker 配置更新报告

**更新时间**: 2026-05-09
**架构变更**: 从旧架构（双进程）更新为新架构（单进程）

---

## 1. 变更内容

### 1.1 Dockerfile.all-in-one（已更新 ✅）

**旧架构**（双进程）：
```dockerfile
FROM opendatalab/mineru:latest

# 复制 MCP Server
COPY mcp-server/ /app/mcp-server/

# 复制启动脚本
COPY scripts/start-all-in-one.sh /app/start.sh

# 暴露双端口
EXPOSE 8000 8001

# 启动脚本（管理两个进程）
CMD ["/app/start.sh"]
```

**新架构**（单进程）：
```dockerfile
FROM python:3.11-slim

# 复制 MinerU 源码（直接包含）
COPY src/mineru/ /app/mineru/

# 复制 MCP Server 源码
COPY mcp-server/ /app/mcp-server/

# 安装 MinerU 和 MCP Server
RUN pip install -e /app/mineru
RUN pip install -e /app/mcp-server

# 暴露单端口
EXPOSE 8001

# 单命令启动（无启动脚本）
CMD ["mineru-mcp", "--enable-mineru-api"]
```

**关键变更**：
- ✅ 不依赖 MinerU 官方镜像
- ✅ MinerU 源码直接包含在镜像
- ✅ 单端口（8001）
- ✅ 无启动脚本（单命令启动）

---

### 1.2 docker-compose.yml（已更新 ✅）

**旧架构**：
```yaml
ports:
  - "8000:8000"  # MinerU FastAPI
  - "8001:8001"  # MCP Server

environment:
  - MINERU_API_BASE=http://localhost:8000  # MCP 调用 MinerU API
```

**新架构**：
```yaml
ports:
  - "8001:8001"  # 单端口（MCP + API + MinerU Native）

environment:
  # 无 MINERU_API_BASE（MinerU 内嵌）
```

**关键变更**：
- ✅ 单端口映射（8001）
- ✅ 无 MINERU_API_BASE 配置（MinerU 内嵌）

---

### 1.3 scripts/start-all-in-one.sh（已删除 ✅）

**原因**：新架构无需启动脚本，直接单命令启动。

---

### 1.4 docker/README.md（已更新 ✅）

**新增内容**：
- ✅ 新架构说明（单进程）
- ✅ 旧架构对比（已废弃）
- ✅ 使用指南（单命令启动）

---

## 2. 架构对比

### 2.1 新架构（单进程，推荐 ✅）

```
单进程（uvicorn，端口 8001）
│
├── /mcp          → MCP Tools（FastMCP）
├── /api          → REST API（FastAPI）
└── /mineru_api   → MinerU Native API（内嵌挂载）
```

**启动命令**：
```bash
mineru-mcp --enable-mineru-api
```

**Docker 启动**：
```bash
docker-compose up -d  # 单进程启动
```

---

### 2.2 旧架构（双进程，已废弃）

```
进程 1: MinerU FastAPI（端口 8000）
进程 2: MCP Server（端口 8001） → HTTP → 进程 1
```

**启动脚本**：
```bash
/app/start.sh
# 启动 MinerU FastAPI（端口 8000）
# 启动 MCP Server（端口 8001）
# 等待两个进程
```

---

## 3. 优势对比

| 特性 | 旧架构（双进程） | 新架构（单进程） |
|------|----------------|----------------|
| **进程数** | ❌ 2 个进程 | ✅ 1 个进程 |
| **端口数** | ❌ 2 个端口（8000 + 8001） | ✅ 1 个端口（8001） |
| **启动复杂度** | ❌ 需启动脚本管理 2 个进程 | ✅ 单命令启动 |
| **调用路径** | ❌ MCP → HTTP → MinerU（绕路） | ✅ MinerU 内嵌（高效） |
| **容器管理** | ⚠️ 需监控 2 个进程 | ✅ 单进程，简单监控 |
| **Dockerfile** | ⚠️ 依赖 MinerU 官方镜像 | ✅ 完全独立构建 |

---

## 4. 使用示例

### 4.1 构建并启动（新架构）

```bash
# 构建镜像
docker-compose build

# 启动容器
docker-compose up -d

# 查看日志
docker logs mineru-mcp-all-in-one

# 访问服务（单端口）
curl http://localhost:8001/health          # 健康检查
curl http://localhost:8001/api/health      # REST API
curl http://localhost:8001/mineru_api/health # MinerU Native
```

---

### 4.2 环境变量配置

```bash
# .env 文件
MINERU_VLM_BASE_URL=http://vlm-server:30000/v1
MINERU_VLM_API_KEY=your-api-key
MINERU_DEFAULT_BACKEND=hybrid-http-client
MCP_LOG_LEVEL=INFO
```

---

## 5. 变更文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `docker/Dockerfile.all-in-one` | ✅ 已更新 | 新架构（单进程） |
| `docker/docker-compose.yml` | ✅ 已更新 | 单端口配置 |
| `docker/README.md` | ✅ 已更新 | 新架构说明 |
| `scripts/start-all-in-one.sh` | ✅ 已删除 | 不需要启动脚本 |
| `docker/Dockerfile.mcp-only` | ✅ 保持 | 分离模式（可选） |
| `docker/docker-compose.separated.yml` | ✅ 保持 | 分离模式（可选） |

---

## 6. 总结

✅ **Docker 配置已更新为新架构（单进程）**

**关键改进**：
- ✅ 单进程启动（无启动脚本）
- ✅ 单端口访问（8001）
- ✅ MinerU 内嵌（高效调用）
- ✅ 完全独立构建（不依赖官方镜像）

**架构对比**：
- 旧架构：双进程，双端口，启动脚本管理
- 新架构：单进程，单端口，单命令启动

**使用建议**：
- ✅ 推荐使用新架构（All-in-One）
- ⚠️ 旧架构已废弃（仅保留分离模式）

---

✌Bazinga！