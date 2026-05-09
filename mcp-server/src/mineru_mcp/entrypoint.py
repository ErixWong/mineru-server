"""
All-in-One Container Entrypoint

Starts MinerU FastAPI + MCP Server (REST API + MCP) in a single process
on a single port. No child process needed.

Usage:
    python -m mineru.mcp.entrypoint

Environment Variables:
    MCP_HTTP_HOST: HTTP host (default: 0.0.0.0)
    MCP_HTTP_PORT: HTTP port (default: 8000)
"""

import os
import sys

from loguru import logger


def main() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(sys.stderr, level=log_level)

    # In all-in-one mode, MinerU is mounted at /mineru, no external backend needed
    os.environ.setdefault("MCP_SERVER_MODE", "http")

    host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    port_str = os.getenv("MCP_HTTP_PORT", "8000")
    try:
        port = int(port_str)
    except ValueError:
        logger.error(f"Invalid MCP_HTTP_PORT: {port_str}")
        sys.exit(1)

    # MinerUClient should call the locally mounted /mineru sub-app
    os.environ["MINERU_API_BASE"] = f"http://127.0.0.1:{port}/mineru"

    logger.info("=== MinerU All-in-One Container ===")
    logger.info(f"Single-port mode: {host}:{port}")
    logger.info("  /mineru/  - MinerU FastAPI (PDF parsing)")
    logger.info("  /api/     - MCP REST API")
    logger.info("  /mcp/     - MCP SSE/HTTP")

    from mineru_mcp.app import run_unified_server

    run_unified_server(
        host=host,
        port=port,
        enable_api=True,
        enable_mcp=True,
        enable_mineru=True,
    )


if __name__ == "__main__":
    main()
