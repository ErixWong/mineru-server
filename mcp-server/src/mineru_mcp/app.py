"""
Unified Starlette Application

Mounts both REST API (FastAPI) and MCP (SSE + Streamable HTTP) under a
single Starlette app, following the same pattern as markitdown-server.

Auto-discovers MinerU package - no need to pip install!
"""

import contextlib
import os
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

# Auto-add MinerU to Python path (no need to pip install)
# ✅ 正确：添加 MinerU 的父目录（包含 mineru 包）
_mineru_paths = [
    # Try multiple possible locations (relative to this file)
    Path(__file__).parent.parent.parent.parent / "src" / "mineru",  # ../../../../src/mineru
    Path(__file__).parent.parent.parent / "mineru",  # ../../../mineru
    Path.cwd() / "src" / "mineru",  # current_dir/src/mineru
]

for mineru_path in _mineru_paths:
    if mineru_path.exists() and str(mineru_path) not in sys.path:
        sys.path.insert(0, str(mineru_path))
        break

import uvicorn
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from mineru_mcp.api import create_api_app
from mineru_mcp.server import create_mcp_server
from mineru_mcp.config import get_config


_start_time = time.time()


def create_unified_app(
    enable_api: bool = True,
    enable_mcp: bool = True,
    enable_mineru_api: bool = False,
) -> Starlette:
    """Create a unified Starlette app with optional API, MCP, and MinerU services.

    Args:
        enable_api: Mount the REST API under /api.
        enable_mcp: Mount MCP SSE and Streamable HTTP endpoints.
        enable_mineru_api: Mount MinerU native API under /mineru_api (proxy mode).

    Returns:
        Starlette application instance.
        
    Architecture:
        - /mcp          → MCP Tools (MCP protocol for Claude Desktop/Cline)
        - /api          → MCP Server REST API (enhanced features)
        - /mineru_api   → MinerU native API (proxy to MinerU FastAPI)
    """
    config = get_config()
    services = []
    if enable_api:
        services.append("api")
    if enable_mcp:
        services.append("mcp")
    if enable_mineru_api:
        services.append("mineru_api")

    async def root_health(request: Request):
        return JSONResponse({
            "status": "healthy",
            "services": services,
            "uptime": time.time() - _start_time,
        })

    routes: list = [
        Route("/", root_health),
        Route("/health", root_health),
    ]

    if enable_api:
        api_app = create_api_app()
        routes.append(Mount("/api", app=api_app))

    if enable_mineru_api:
        # Mount MinerU native API under /mineru_api (proxy mode)
        from mineru.cli.fast_api import create_app as create_mineru_app
        mineru_app = create_mineru_app()
        routes.append(Mount("/mineru_api", app=mineru_app))

    session_manager: Optional[StreamableHTTPSessionManager] = None

    if enable_mcp:
        mcp_server = create_mcp_server(config)
        raw_server = mcp_server._mcp_server

        use_streaming = os.getenv(
            "MINERU_MCP_STREAMING", "false"
        ).lower() == "true"
        mcp_messages_path = "/mcp/messages/"
        sse = SseServerTransport(mcp_messages_path)
        session_manager = StreamableHTTPSessionManager(
            app=raw_server,
            event_store=None,
            json_response=not use_streaming,
            stateless=True,
        )

        async def handle_mcp_sse(request: Request) -> None:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await raw_server.run(
                    read_stream,
                    write_stream,
                    raw_server.create_initialization_options(),
                )

        async def handle_streamable_http(
            scope: Scope, receive: Receive, send: Send
        ) -> None:
            method = scope.get("method", "GET")
            if method == "GET" and session_manager.stateless:
                response = Response(
                    content='{"error":"Method Not Allowed: Standalone SSE stream not available in stateless mode."}',
                    status_code=405,
                    headers={"Allow": "POST"},
                )
                await response(scope, receive, send)
                return
            await session_manager.handle_request(scope, receive, send)

        routes.extend([
            Route("/mcp/sse", endpoint=handle_mcp_sse),
            Mount("/mcp/messages/", app=sse.handle_post_message),
            Mount("/mcp", app=handle_streamable_http),
        ])

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        if enable_mcp and session_manager:
            async with session_manager.run():
                yield
        else:
            yield

    cors_origins = os.getenv("MINERU_CORS_ORIGINS", "*")
    if cors_origins != "*":
        cors_origins = [origin.strip() for origin in cors_origins.split(",")]

    return Starlette(
        routes=routes,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
        lifespan=lifespan,
    )


def run_unified_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
    enable_api: bool = True,
    enable_mcp: bool = True,
    enable_mineru_api: bool = False,
):
    """Start the unified server with uvicorn."""
    config = get_config()
    host = host or config.http_host
    port = port or config.http_port

    active = []
    if enable_api:
        active.append("api")
    if enable_mcp:
        active.append("mcp")
    if enable_mineru_api:
        active.append("mineru_api")

    print(f"\nMinerU MCP Server starting...")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    if not enable_mineru_api:
        print(f"  MinerU API: {config.mineru_api_base}")
    print(f"  Services: {', '.join(active)}")
    print(f"  Endpoints:")
    if enable_mineru_api:
        print(f"    MinerU Native API:  http://{host}:{port}/mineru_api/")
        print(f"    MinerU Native Docs: http://{host}:{port}/mineru_api/docs")
    if enable_api:
        print(f"    MCP Server API:     http://{host}:{port}/api/")
        print(f"    API Docs:           http://{host}:{port}/api/docs")
    if enable_mcp:
        print(f"    MCP SSE:            http://{host}:{port}/mcp/sse")
        print(f"    MCP HTTP:           http://{host}:{port}/mcp")
    print()

    app = create_unified_app(
        enable_api=enable_api,
        enable_mcp=enable_mcp,
        enable_mineru_api=enable_mineru_api,
    )
    uvicorn.run(app, host=host, port=port)
