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

from mineru_mcp.config import get_config
from mineru_mcp.auth import check_auth_header


_task_scheduler = None
_start_time = time.time()


class AuthMiddleware:
    """Authentication middleware for HTTP requests.
    
    Validates Bearer token in Authorization header.
    Bypasses authentication for health endpoints and when auth is not configured.
    """
    
    def __init__(self, app):
        self.app = app
        
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        
        # Bypass auth for health endpoints (root and /health)
        if path in ("/", "/health", "/api/health"):
            await self.app(scope, receive, send)
            return
        
        # Bypass auth for OPTIONS requests (CORS preflight)
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        
        # Check authentication
        headers = dict(scope["headers"])
        # Starlette headers are lowercase bytes: b"authorization"
        auth_header = headers.get(b"authorization", b"").decode("utf-8")
        
        error = check_auth_header(auth_header)
        if error:
            response = JSONResponse(
                error.to_dict(),
                status_code=error.http_status
            )
            await response(scope, receive, send)
            return
        
        # Auth passed, continue to app
        await self.app(scope, receive, send)


def create_api_app(config=None):
    """Create REST API app.
    
    Args:
        config: MCP configuration.
        
    Returns:
        FastAPI application instance.
    """
    from mineru_mcp.api import create_api_app as create_api_impl
    return create_api_impl()


def create_mcp_server(config):
    """Create MCP server.
    
    Args:
        config: MCP configuration.
        
    Returns:
        FastMCP server instance.
    """
    from mineru_mcp.server import create_mcp_server as create_server_impl
    return create_server_impl(config)


def create_unified_app(
    enable_api: bool = True,
    enable_mcp: bool = True,
) -> Starlette:
    """Create a unified Starlette app with API and MCP services.

    Args:
        enable_api: Mount the REST API under /api.
        enable_mcp: Mount MCP SSE and Streamable HTTP endpoints.

    Returns:
        Starlette application instance.
        
    Architecture:
        - /mcp          → MCP Tools (MCP protocol for Claude Desktop/Cline)
        - /api          → REST API (task submission and query)
    """
    config = get_config()
    services = []
    if enable_api:
        services.append("api")
    if enable_mcp:
        services.append("mcp")

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
        api_app = create_api_app(config)
        routes.append(Mount("/api", app=api_app))

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
        global _task_scheduler
        
        from mineru_mcp.task_queue import TaskDatabase, TaskProcessor, TaskScheduler
        from loguru import logger
        
        config = get_config()
        
        logger.info("Initializing task queue...")
        
        db = TaskDatabase(db_path=config.db_path)
        processor = TaskProcessor(db=db, max_concurrent=config.max_concurrent)
        scheduler = TaskScheduler(
            processor=processor,
            db=db,
            max_concurrent=config.max_concurrent,
            poll_interval=1.0,
            timeout_check_enabled=True
        )
        
        _task_scheduler = scheduler
        
        recovered = scheduler.recover_processing_tasks()
        if recovered > 0:
            logger.info(f"Recovered {recovered} tasks from previous session")
        
        await scheduler.start()
        logger.info(f"Task scheduler started (max_concurrent={config.max_concurrent})")
        
        try:
            if enable_mcp and session_manager:
                async with session_manager.run():
                    yield
            else:
                yield
        finally:
            if _task_scheduler:
                await _task_scheduler.stop()
                logger.info("Task scheduler stopped")

    cors_origins = os.getenv("MINERU_CORS_ORIGINS", "*")
    if cors_origins != "*":
        cors_origins = [origin.strip() for origin in cors_origins.split(",")]

    return Starlette(
        routes=routes,
        middleware=[
            Middleware(AuthMiddleware),
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

    print(f"\n{'='*50}")
    print(f"MinerU MCP Server starting...")
    print(f"{'='*50}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Services: {', '.join(active)}")
    print(f"  Endpoints:")
    if enable_api:
        print(f"    REST API:     http://{host}:{port}/api/")
        print(f"    API Docs:     http://{host}:{port}/api/docs")
    if enable_mcp:
        print(f"    MCP SSE:      http://{host}:{port}/mcp/sse")
        print(f"    MCP HTTP:     http://{host}:{port}/mcp")
    print(f"\n  [!] Server is running. DO NOT CLOSE this window!")
    print(f"  [!] Press CTRL+C to stop the server.")
    print(f"{'='*50}\n")

    app = create_unified_app(
        enable_api=enable_api,
        enable_mcp=enable_mcp,
    )
    uvicorn.run(app, host=host, port=port)
