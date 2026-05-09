# MinerU MCP Server - All-in-One Dockerfile
# 独立构建，可推送到 Docker Hub
# 单进程架构：MCP + API + MinerU Native（端口 8001）

FROM python:3.11-slim

LABEL maintainer="ErixWong"
LABEL description="MinerU MCP Server - All-in-One (MCP + API + MinerU Native)"
LABEL version="1.0.0"
LABEL architecture="single-process"

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    fonts-noto-core \
    fonts-noto-cjk \
    fontconfig \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建应用目录
WORKDIR /app

# 复制 MinerU 源码（完整代码，不从 PyPI 安装）
COPY src/mineru/ /app/mineru/

# 复制 MCP Server 源码
COPY mcp-server/ /app/mcp-server/

# 安装 MinerU（从本地源码，包含所有依赖）
WORKDIR /app/mineru
RUN pip install --no-cache-dir -e .

# 安装 MCP Server（从本地源码）
WORKDIR /app/mcp-server
RUN pip install --no-cache-dir -e .

# 创建必要目录
RUN mkdir -p /app/output /app/input

# 暴露端口（单端口 8001）
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 环境变量默认值
ENV MCP_SERVER_MODE=http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8001 \
    MINERU_OUTPUT_ROOT=/app/output \
    MCP_LOG_LEVEL=INFO \
    MINERU_DEFAULT_BACKEND=hybrid-http-client \
    MINERU_MODEL_SOURCE=local

# 启动服务（单进程，单命令）
CMD ["mineru-mcp", "--mode", "http", "--port", "8001", "--enable-mineru-api"]