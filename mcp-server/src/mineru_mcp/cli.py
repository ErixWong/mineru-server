"""
MCP Server CLI Entry Point

Command-line interface for running the MinerU MCP Server.
"""

import click
from dataclasses import replace
from pathlib import Path
from loguru import logger

from dotenv import load_dotenv

from mineru_mcp.config import get_config, MCPConfig, reset_config
from mineru_mcp.server import create_mcp_server
from mineru_mcp import __version__


@click.command()
@click.option(
    "--mode",
    type=click.Choice(["stdio", "http"]),
    default=None,
    help="Server mode: stdio (for Claude Desktop) or http (for remote calls)",
)
@click.option(
    "--host",
    default=None,
    help="HTTP server host (only for http mode)",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="HTTP server port (only for http mode)",
)
@click.option(
    "--mineru-api-base",
    default=None,
    help="MinerU FastAPI base URL (default: http://localhost:8000)",
)
@click.option(
    "--log-level",
    default=None,
    help="Log level (DEBUG, INFO, WARNING, ERROR)",
)
@click.option(
    "--no-api",
    is_flag=True,
    default=False,
    help="Disable REST API endpoints (http mode only)",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    default=False,
    help="Disable MCP endpoints (http mode only)",
)
@click.option(
    "--enable-mineru-api",
    is_flag=True,
    default=False,
    help="Enable MinerU native API proxy (mount under /mineru_api)",
)
@click.version_option(version=__version__, prog_name="mineru-mcp")
def main(
    mode: str | None,
    host: str | None,
    port: int | None,
    mineru_api_base: str | None,
    log_level: str | None,
    no_api: bool,
    no_mcp: bool,
    enable_mineru_api: bool,
) -> None:
    """MinerU MCP Server - Expose MinerU PDF parsing via MCP protocol.

    This server can run in two modes:

    1. stdio mode (default): For desktop MCP clients like Claude Desktop or Cline.
       The server communicates via stdin/stdout using the MCP protocol.

    2. http mode: For remote HTTP calls with optional REST API.
       The server runs as an HTTP server with both MCP and REST endpoints.

    3. Proxy mode (--enable-mineru-api): Mount MinerU native API under /mineru_api.
       MinerU FastAPI is proxied, providing direct access to native endpoints.

    Architecture:
        - /mcp          → MCP Tools (MCP protocol)
        - /api          → MCP Server REST API (enhanced features)
        - /mineru_api   → MinerU native API (proxy)

    Examples:

        # stdio mode (for Claude Desktop)
        mineru-mcp

        # HTTP mode (MCP + REST API)
        mineru-mcp --mode http --port 8001

        # Proxy mode (MCP + API + MinerU native API)
        mineru-mcp --mode http --port 8001 --enable-mineru-api

        # HTTP mode, REST API only
        mineru-mcp --mode http --port 8001 --no-mcp

        # HTTP mode, MCP only
        mineru-mcp --mode http --port 8001 --no-api

        # Custom MinerU API URL (if MinerU is remote)
        mineru-mcp --mineru-api-base http://mineru-api:8000
    """
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug(f"Loaded .env from: {env_path}")

    reset_config()

    base_config = get_config()

    config_overrides = {}
    if mode:
        config_overrides["server_mode"] = mode
    if host:
        config_overrides["http_host"] = host
    if port:
        config_overrides["http_port"] = port
    if mineru_api_base:
        config_overrides["mineru_api_base"] = mineru_api_base
    if log_level:
        config_overrides["log_level"] = log_level

    config = replace(base_config, **config_overrides) if config_overrides else base_config

    logger.info(f"Starting MinerU MCP Server in {config.server_mode} mode")
    if enable_mineru_api:
        logger.info("Proxy mode enabled - MinerU native API will be mounted under /mineru_api")
    else:
        logger.info(f"MinerU API: {config.mineru_api_base}")

    if config.is_stdio_mode():
        server = create_mcp_server(config)
        server.run(transport="stdio")
    else:
        from mineru_mcp.app import run_unified_server
        run_unified_server(
            host=config.http_host if host else None,
            port=config.http_port if port else None,
            enable_api=not no_api,
            enable_mcp=not no_mcp,
            enable_mineru_api=enable_mineru_api,
        )


if __name__ == "__main__":
    main()
