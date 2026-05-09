#!/bin/bash
# All-in-One 启动脚本
# 同时启动 MinerU FastAPI 和 MCP Server

set -e

echo "========================================"
echo "Starting MinerU + MCP Server (All-in-One)"
echo "========================================"

# 启动 MinerU FastAPI (端口 8000)
echo "[1/2] Starting MinerU FastAPI on port 8000..."
cd /app/src/mineru
uvicorn mineru.cli.fast_api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    &

MINERU_PID=$!
echo "MinerU FastAPI started (PID: $MINERU_PID)"

# 等待 MinerU 启动
echo "Waiting for MinerU to be ready..."
sleep 10
for i in {1..30}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "MinerU FastAPI is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# 启动 MCP Server (端口 8001)
echo "[2/2] Starting MCP Server on port 8001..."
cd /app/mcp-server
mineru-mcp \
    --mode http \
    --host 0.0.0.0 \
    --port 8001 \
    &

MCP_PID=$!
echo "MCP Server started (PID: $MCP_PID)"

echo "========================================"
echo "All services started!"
echo "========================================"
echo "MinerU FastAPI: http://localhost:8000"
echo "MinerU Docs:    http://localhost:8000/docs"
echo "MCP Server:     http://localhost:8001"
echo "MCP API Docs:   http://localhost:8001/api/docs"
echo "MCP SSE:        http://localhost:8001/mcp/sse"
echo "========================================"

# 等待所有进程
wait $MINERU_PID $MCP_PID