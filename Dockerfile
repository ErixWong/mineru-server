# MinerU MCP Server - All-in-One Dockerfile
# 多阶段构建：前端 SPA + Python API/MCP + MinerU Native

FROM node:20-bookworm-slim AS admin-ui-builder

WORKDIR /build/admin-ui

COPY mcp-server/admin-ui/package.json mcp-server/admin-ui/package-lock.json ./
RUN npm ci

COPY mcp-server/admin-ui/ ./
RUN npm run build


FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="ErixWong"
LABEL description="MinerU MCP Server - All-in-One (Admin SPA + API + MCP + MinerU Native)"
LABEL version="1.0.0"
LABEL architecture="single-process"

# 安装系统依赖（OpenCV、CJK 字体，以及 vLLM / Triton 运行时所需工具）
# 固定 bookworm，避免 python:3.11-slim 随上游漂移到 trixie 后引入构建不稳定性
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    gcc \
    g++ \
    build-essential \
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
ARG MINERU_REF=mineru-3.4.4-released
RUN git clone --depth 1 --branch ${MINERU_REF} https://github.com/opendatalab/MinerU.git /app/mineru-src

# 复制 MCP Server 源码
COPY mcp-server/ /app/mcp-server/

# 复制前端构建产物到后端期望目录
COPY --from=admin-ui-builder /build/admin-ui/dist/ /app/mcp-server/admin-ui/dist/

# 安装 MinerU（从 git clone 的源码，包含核心依赖与 vLLM 扩展）
WORKDIR /app/mineru-src
RUN pip install --no-cache-dir -e ".[core,vllm]"

# 安装 MCP Server（从本地源码）
WORKDIR /app/mcp-server
RUN pip install --no-cache-dir -e .

# 创建必要目录
RUN mkdir -p /app/output /app/input /root/.mineru

# 暴露端口（单端口 8002）
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# ===========================================
# Environment Variables
# ===========================================
# MCP Server Configuration
ENV MCP_SERVER_MODE=http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8002 \
    MCP_LOG_LEVEL=INFO

# MinerU Configuration
ENV MINERU_OUTPUT_ROOT=/app/output \
    MINERU_DEFAULT_BACKEND=hybrid-http-client \
    MINERU_VLLM_DEVICE=cuda \
    VLLM_USE_V1=1 \
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

# Authentication
# HTTP / MCP requests use caller API keys created in the admin console.
# Send them as: Authorization: Bearer <caller_api_key>

# 启动服务（单进程，单命令）
CMD ["mineru-mcp", "--mode", "http", "--port", "8002"]
