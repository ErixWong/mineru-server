"""Unified Starlette application.

Mounts both REST API (FastAPI) and MCP (SSE + Streamable HTTP) under a single
Starlette app, following the same pattern as markitdown-server.
"""

import contextlib
import os
import time
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Optional

import uvicorn
from loguru import logger
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from mineru_mcp.config import get_config
from mineru_mcp.auth import check_auth_header, resolve_principal
from mineru_mcp.errors import MCPError
from mineru_mcp.principal import set_current_principal, clear_current_principal
from mineru_mcp.models import HealthResponse
from mineru_mcp import __version__
from fastapi import FastAPI


_task_scheduler = None
_postprocess_runner = None
_start_time = time.time()


class AuthMiddleware:
    """Authentication middleware for HTTP requests.
    
    Validates Bearer token in Authorization header.
    Resolves the current principal and stores it in request state.
    Bypasses authentication for health endpoints and when auth is not configured.
    """
    
    def __init__(self, app):
        self.app = app
        
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Keep /mcp and /mcp/ equivalent without relying on framework redirects,
        # so MCP clients do not lose auth headers on a 307 hop.
        if scope.get("path") == "/mcp":
            scope = {
                **scope,
                "path": "/mcp/",
                "raw_path": b"/mcp/",
            }
        
        path = scope.get("path", "")
        
        # Bypass auth for health endpoints (root and /health)
        if path in ("/", "/health", "/api/health"):
            await self.app(scope, receive, send)
            return
        
        # Bypass auth for admin console pages and admin API.
        # Admin SPA uses its own session-cookie + CSRF model via admin_api.py,
        # so it must not be blocked by the outer Bearer-token middleware.
        if path.startswith("/admin") or path.startswith("/api/admin"):
            await self.app(scope, receive, send)
            return
        
        # Bypass auth for OPTIONS requests (CORS preflight)
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        
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
        
        try:
            principal = resolve_principal(auth_header)
        except MCPError as e:
            # Authentication failed — return structured error
            logger.warning(f"Authentication failed: {e.message}")
            response = JSONResponse(
                e.to_dict(),
                status_code=e.http_status
            )
            await response(scope, receive, send)
            return
        
        # Store principal in scope state for REST API access
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["principal"] = principal
        
        # Also set in context variable for MCP tools to access
        set_current_principal(principal)
        
        # Process request
        try:
            await self.app(scope, receive, send)
        finally:
            # Clean up context variable after request
            clear_current_principal()


class SecurityHeadersMiddleware:
    """Apply baseline security headers, with stricter rules for admin surfaces."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])

                if path.startswith("/admin") or path.startswith("/api/admin"):
                    headers.extend([
                        (b"cache-control", b"no-store"),
                        (b"x-frame-options", b"DENY"),
                        (b"content-security-policy", b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                    ])
            await send(message)

        await self.app(scope, receive, send_with_headers)


class PublicAPICORSMiddleware:
    """Apply CORS to public API routes while keeping admin surfaces same-origin."""

    def __init__(self, app):
        cors_origins = os.getenv("MINERU_CORS_ORIGINS", "*")
        self.app = app
        self.allow_all_origins = cors_origins.strip() == "*"
        self.allowed_origins = [item.strip() for item in cors_origins.split(",") if item.strip()] if not self.allow_all_origins else []

        self.cors_app = CORSMiddleware(
            app,
            allow_origins=[] if self.allow_all_origins else self.allowed_origins,
            allow_origin_regex=".*" if self.allow_all_origins else None,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api") or path.startswith("/api/admin"):
            await self.app(scope, receive, send)
            return

        await self.cors_app(scope, receive, send)


def _enforce_public_mode_safety() -> None:
    """Fail fast on obviously unsafe public deployment modes."""
    if os.getenv("MINERU_PUBLIC_MODE", "false").lower() != "true":
        return


def create_api_app(config=None):
    """Create REST API app.

    Args:
        config: MCP configuration.

    Returns:
        FastAPI application instance.
    """
    from mineru_mcp.api import create_api_app as create_api_impl
    return create_api_impl()


def get_postprocess_runner():
    """Return the lifespan-managed PostprocessRunner (None before startup)."""
    return _postprocess_runner


def create_console_app() -> FastAPI:
    """Create Admin Console app for HTML pages.
    
    Returns:
        FastAPI application for admin console pages.
    """
    admin_ui_dist = Path(__file__).resolve().parents[2] / "admin-ui" / "dist"

    app = FastAPI(
        title="MinerU Admin Console",
        description="Admin management console",
    )

    if admin_ui_dist.exists():
        admin_ui_dist_resolved = admin_ui_dist.resolve()
        assets_dir = admin_ui_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="admin-assets")

        @app.get("/{full_path:path}")
        async def spa_entry(full_path: str = ""):
            if full_path:
                requested = (admin_ui_dist / full_path).resolve()
                try:
                    requested.relative_to(admin_ui_dist_resolved)
                except ValueError:
                    return Response(status_code=404)
                if requested.is_file():
                    return FileResponse(requested)
            return FileResponse(admin_ui_dist / "index.html")
    else:
        @app.get("/{full_path:path}")
        async def missing_admin_ui(full_path: str = ""):
            return HTMLResponse(
                "<h1>Admin UI not built</h1><p>Run npm install && npm run build in mcp-server/admin-ui.</p>",
                status_code=503,
            )

    return app


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
    _enforce_public_mode_safety()
    services = []
    if enable_api:
        services.append("api")
    if enable_mcp:
        services.append("mcp")

    async def root_health(request: Request):
        """Root health check endpoint (no authentication required).
        
        Returns a simplified health response for basic liveness checks.
        For full health details including queue stats, use /api/health instead.
        
        Note: This is a simplified health check (liveness probe).
              Use /api/health for complete status with queue statistics.
        """
        from mineru_mcp.models import HealthResponse
        from mineru_mcp.auth import is_auth_required
        
        scheduler_running = bool(_task_scheduler and _task_scheduler._running)
        
        status = "healthy" if scheduler_running else "degraded"
        
        return JSONResponse(HealthResponse(
            status=status,
            version=__version__,
            uptime=time.time() - _start_time,
            scheduler_running=scheduler_running,
            auth_required=is_auth_required(),
            queue_stats=None,  # Simplified: no queue stats for basic liveness
        ).model_dump(mode="json"))

    routes: list = [
        Route("/", root_health),
        Route("/health", root_health),
    ]

    if enable_api:
        api_app = create_api_app(config)
        routes.append(Mount("/api", app=api_app))
        
        # Mount admin console HTML pages under /admin (separate from /api)
        console_app = create_console_app()
        routes.append(Mount("/admin", app=console_app))

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
        global _task_scheduler, _postprocess_runner

        from mineru_mcp.task_queue import TaskDatabase, TaskProcessor, TaskScheduler, PostprocessRunner
        from mineru_mcp.admin_auth import init_default_admin
        from loguru import logger

        config = get_config()

        # Initialize default admin account
        logger.info("Initializing admin credentials...")
        init_default_admin()

        logger.info("Initializing task queue...")

        db = TaskDatabase(db_path=config.db_path)
        postprocess_runner = PostprocessRunner(
            db=db,
            max_concurrent=config.postprocess_max_concurrent,
        )
        processor = TaskProcessor(
            db=db,
            max_concurrent=config.max_concurrent,
            postprocess_runner=postprocess_runner,
        )
        scheduler = TaskScheduler(
            processor=processor,
            db=db,
            max_concurrent=config.max_concurrent,
            poll_interval=1.0,
            timeout_check_enabled=True
        )

        _task_scheduler = scheduler
        _postprocess_runner = postprocess_runner

        recovered = scheduler.recover_processing_tasks()
        if recovered > 0:
            logger.info(f"Recovered {recovered} tasks from previous session")

        await scheduler.start()
        logger.info(f"Task scheduler started (max_concurrent={config.max_concurrent})")
        await postprocess_runner.start()
        logger.info(f"Postprocess runner started (max_concurrent={config.postprocess_max_concurrent})")

        try:
            if enable_mcp and session_manager:
                async with session_manager.run():
                    yield
            else:
                yield
        finally:
            if _postprocess_runner:
                await _postprocess_runner.stop()
                logger.info("Postprocess runner stopped")
            if _task_scheduler:
                await _task_scheduler.stop()
                logger.info("Task scheduler stopped")

    return Starlette(
        routes=routes,
        middleware=[
            Middleware(SecurityHeadersMiddleware),
            Middleware(AuthMiddleware),
            Middleware(PublicAPICORSMiddleware),
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
    print(f"\n  [i] Server is running. DO NOT CLOSE this window!")
    print(f"  [i] Press CTRL+C to stop the server.")
    print(f"{'='*50}\n")

    app = create_unified_app(
        enable_api=enable_api,
        enable_mcp=enable_mcp,
    )
    uvicorn.run(app, host=host, port=port)
