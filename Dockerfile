# MinerU MCP Server - All-in-One Dockerfile
# 独立构建，可推送到 Docker Hub
# 单进程架构：MCP + API + MinerU Native（端口 8001）

FROM python:3.11-slim

LABEL maintainer="ErixWong"
LABEL description="MinerU MCP Server - All-in-One (MCP + API + MinerU Native)"
LABEL version="1.0.0"
LABEL architecture="single-process"

# 安装系统依赖（OpenCV 和 CJK 字体）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-core \
    fonts-noto-cjk \
    fontconfig \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建应用目录
WORKDIR /app

# 克隆 MinerU 官方源码（指定版本）
RUN git clone --depth 1 --branch master https://github.com/opendatalab/MinerU.git /app/mineru-src

# 复制 MCP Server 源码
COPY mcp-server/ /app/mcp-server/

# 安装 MinerU（从 git clone 的源码，包含核心依赖）
WORKDIR /app/mineru-src
RUN pip install --no-cache-dir -e ".[core]"

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

# ===========================================
# Environment Variables
# ===========================================
# MCP Server Configuration
ENV MCP_SERVER_MODE=http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8001 \
    MCP_LOG_LEVEL=INFO

# MinerU Configuration
ENV MINERU_OUTPUT_ROOT=/app/output \
    MINERU_DEFAULT_BACKEND=hybrid-http-client \
    MINERU_MODEL_SOURCE=local \
    HF_HOME=/root/.cache/huggingface \
    MODELSCOPE_CACHE=/root/.cache/modelscope

# Task Queue Configuration
# SQLite-based task queue with concurrency control
ENV MINERU_MAX_CONCURRENT=3 \
    MINERU_TASK_TIMEOUT=3600 \
    MINERU_RETRY_LIMIT=3 \
    MINERU_CLEANUP_DAYS=30 \
    MINERU_DB_PATH=/app/output/tasks.db

# Authentication (Optional)
# Set MCP_HTTP_AUTH_TOKEN to enable Bearer Token authentication
# Generate token: python -m mineru_mcp.auth
# ENV MCP_HTTP_AUTH_TOKEN=your-secure-token-here

# 启动服务（单进程，单命令）
CMD ["mineru-mcp", "--mode", "http", "--port", "8001"]