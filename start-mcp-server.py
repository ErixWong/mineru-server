#!/usr/bin/env python3
"""
MinerU MCP Server 启动脚本

支持三种运行模式：
1. stdio 模式（Claude Desktop）
2. HTTP 模式（远程调用）
3. Proxy 模式（MCP + API + MinerU native API）

架构：
    /mcp          → MCP Tools (MCP protocol)
    /api          → MCP Server REST API (enhanced features)
    /mineru_api   → MinerU native API (proxy)

使用方法：
    # stdio 模式
    python start-mcp-server.py
    
    # HTTP 模式
    python start-mcp-server.py --mode http --port 8001
    
    # Proxy 模式（推荐）
    python start-mcp-server.py --mode http --port 8001 --enable-mineru-api
"""

import sys
from pathlib import Path

# 自动添加 MCP Server 和 MinerU 到 Python 路径
_mcp_server_src = Path(__file__).parent / "mcp-server" / "src"
_mineru_parent = Path(__file__).parent / "src" / "mineru"  # ✅ 修复：父目录

if _mcp_server_src.exists():
    sys.path.insert(0, str(_mcp_server_src))
    
if _mineru_parent.exists():
    sys.path.insert(0, str(_mineru_parent))

# 导入并运行 CLI
from mineru_mcp.cli import main

if __name__ == "__main__":
    main()