# Docker Hub 推送指南

**目标**: 将 MinerU MCP Server 推送到 Docker Hub
**镜像**: `erixwong/mineru-mcp:latest`

---

## 1. 构建镜像（独立 Dockerfile）

**Dockerfile 位置**: 项目根目录 `Dockerfile`

**构建命令**:
```bash
# 在项目根目录执行
docker build -t erixwong/mineru-mcp:latest .
```

**构建参数**（可选）:
```bash
# 指定版本号
docker build -t erixwong/mineru-mcp:1.0.0 .

# 不使用缓存（强制重新构建）
docker build --no-cache -t erixwong/mineru-mcp:latest .
```

---

## 2. 测试镜像（本地运行）

**运行容器**:
```bash
docker run -d \
  --name mineru-mcp \
  -p 8001:8001 \
  -v ./output:/app/output \
  -v ./input:/app/input \
  -e MINERU_VLM_BASE_URL=http://your-vlm-server:30000/v1 \
  -e MINERU_VLM_API_KEY=your-api-key \
  erixwong/mineru-mcp:latest
```

**查看日志**:
```bash
docker logs mineru-mcp
```

**测试服务**:
```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/health
curl http://localhost:8001/mineru_api/health
```

---

## 3. 推送到 Docker Hub

**登录 Docker Hub**:
```bash
docker login
# 输入用户名: erixwong
# 输入密码: your-docker-hub-password
```

**推送镜像**:
```bash
docker push erixwong/mineru-mcp:latest
```

**推送指定版本**:
```bash
docker push erixwong/mineru-mcp:1.0.0
```

---

## 4. 使用 Docker Hub 镜像

**拉取镜像**:
```bash
docker pull erixwong/mineru-mcp:latest
```

**运行容器**:
```bash
docker run -d \
  --name mineru-mcp \
  -p 8001:8001 \
  -e MINERU_VLM_BASE_URL=${VLM_URL} \
  -e MINERU_VLM_API_KEY=${VLM_KEY} \
  erixwong/mineru-mcp:latest
```

---

## 5. Docker Hub 镜像信息

**镜像地址**: https://hub.docker.com/r/erixwong/mineru-mcp

**镜像内容**:
- MinerU 源码（完整，不从 PyPI 安装）
- MCP Server（MCP + API）
- MinerU Native API（内嵌）
- 单进程架构（端口 8001）

**镜像大小**: ~2GB（包含 MinerU 所有依赖）

---

## 6. 验证镜像内容

**检查镜像层**:
```bash
docker history erixwong/mineru-mcp:latest
```

**检查镜像大小**:
```bash
docker images erixwong/mineru-mcp
```

**检查构建来源**:
```bash
docker inspect erixwong/mineru-mcp:latest | grep -A 10 "Labels"
```

---

## 7. 完整示例（从构建到推送）

```bash
# 1. 克隆仓库
git clone https://github.com/ErixWong/MinerU.git
cd MinerU

# 2. 构建镜像
docker build -t erixwong/mineru-mcp:latest .

# 3. 本地测试
docker run -d -p 8001:8001 --name test-mineru erixwong/mineru-mcp:latest
curl http://localhost:8001/health
docker stop test-mineru
docker rm test-mineru

# 4. 登录 Docker Hub
docker login

# 5. 推送镜像
docker push erixwong/mineru-mcp:latest

# 6. 清理本地镜像（可选）
docker rmi erixwong/mineru-mcp:latest
```

---

## 8. 对比：Dockerfile vs docker-compose

| 方式 | Dockerfile | docker-compose.yml |
|------|-----------|-------------------|
| **构建命令** | `docker build -t myimage .` | `docker-compose build` |
| **推送支持** | ✅ 可推送到 Docker Hub | ⚠️ 需额外配置 |
| **适用场景** | ✅ 发布镜像到 Docker Hub | ✅ 本地开发测试 |
| **独立性** | ✅ 完全独立 | ⚠️ 依赖 compose 文件 |

---

## 9. 关键说明

**为什么不从 PyPI 安装？**

我们的 Dockerfile **不从 PyPI 安装 MinerU**：
```dockerfile
# ❌ MinerU 官方方式（从 PyPI）
RUN pip install 'mineru[core]>=3.0.0'

# ✅ 我们的方式（从本地源码）
COPY src/mineru/ /app/mineru/
RUN pip install -e .
```

**原因**：
- ✅ 包含 MinerU 最新源码（包含本地修改）
- ✅ 不依赖 PyPI 发布周期
- ✅ 完全控制镜像内容

---

## 10. 注意事项

**GPU 支持**（可选）:
```bash
docker run --gpus all -p 8001:8001 erixwong/mineru-mcp:latest
```

**环境变量配置**:
```bash
docker run \
  -e MINERU_VLM_BASE_URL=http://vlm:30000/v1 \
  -e MINERU_VLM_API_KEY=sk-xxx \
  -e MCP_HTTP_AUTH_TOKEN=secret-token \
  erixwong/mineru-mcp:latest
```

**数据持久化**:
```bash
docker run \
  -v /path/to/output:/app/output \
  -v /path/to/input:/app/input \
  erixwong/mineru-mcp:latest
```

---

## 总结

✅ **独立 Dockerfile 在项目根目录**（Dockerfile）
✅ **可直接构建并推送到 Docker Hub**
✅ **从本地源码安装 MinerU**（不从 PyPI）
✅ **单进程架构**（MCP + API + MinerU Native）

**推送命令**:
```bash
docker build -t erixwong/mineru-mcp:latest .
docker push erixwong/mineru-mcp:latest
```

---

✌Bazinga！