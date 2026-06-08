"""
MCP Server Configuration

Environment variables for MCP Server configuration.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


# Default backend options
DEFAULT_BACKEND = "hybrid-http-client"
VALID_BACKENDS = [
    "pipeline",
    "vlm-auto-engine",
    "vlm-http-client",
    "hybrid-auto-engine",
    "hybrid-http-client",
]


@dataclass
class MCPConfig:
    """MCP Server configuration from environment variables."""
    
    # MinerU Backend configuration
    default_backend: str  # Default parsing backend
    
    # VLM API configuration (for http-client backends)
    vlm_base_url: Optional[str]  # VLM API base URL (e.g., https://api.openai.com/v1)
    vlm_api_key: Optional[str]  # VLM API key
    vlm_model: Optional[str]  # VLM model name
    
    # Title optimization LLM configuration (optional)
    title_api_key: Optional[str]
    title_base_url: Optional[str]
    title_model: Optional[str]
    
    # MCP Server configuration
    server_name: str
    server_mode: str  # "stdio" or "http"
    http_host: str
    http_port: int
    
    # HTTP authentication (optional)
    http_auth_token: Optional[str]
    
    # Logging
    log_level: str
    
    # Task queue configuration
    max_concurrent: int
    task_timeout: int
    retry_limit: int
    cleanup_days: int
    db_path: str
    output_root: str
    
    @classmethod
    def from_env(cls) -> "MCPConfig":
        """Load configuration from environment variables."""
        default_backend = os.getenv("MINERU_DEFAULT_BACKEND", DEFAULT_BACKEND)
        if default_backend not in VALID_BACKENDS:
            default_backend = DEFAULT_BACKEND

        try:
            http_port = int(os.getenv("MCP_HTTP_PORT", "8082") or "8082")
        except ValueError:
            http_port = 8082
        
        try:
            max_concurrent = int(os.getenv("MINERU_MAX_CONCURRENT", "3") or "3")
            max_concurrent = max(1, min(100, max_concurrent))  # Range: 1-100
        except ValueError:
            max_concurrent = 3
        
        try:
            task_timeout = int(os.getenv("MINERU_TASK_TIMEOUT", "3600") or "3600")
        except ValueError:
            task_timeout = 3600
        
        try:
            retry_limit = int(os.getenv("MINERU_RETRY_LIMIT", "3") or "3")
        except ValueError:
            retry_limit = 3
        
        try:
            cleanup_days = int(os.getenv("MINERU_CLEANUP_DAYS", "30") or "30")
        except ValueError:
            cleanup_days = 30
        
        return cls(
            default_backend=default_backend,
            # VLM API configuration
            vlm_base_url=os.getenv("MINERU_VLM_BASE_URL"),
            vlm_api_key=os.getenv("MINERU_VLM_API_KEY"),
            vlm_model=os.getenv("MINERU_VLM_MODEL"),
            # Title optimization LLM configuration
            title_api_key=os.getenv("MINERU_TITLE_API_KEY"),
            title_base_url=os.getenv("MINERU_TITLE_BASE_URL"),
            title_model=os.getenv("MINERU_TITLE_MODEL"),
            # MCP Server configuration
            server_name=os.getenv("MCP_SERVER_NAME", "MinerU MCP Server"),
            server_mode=os.getenv("MCP_SERVER_MODE", "stdio"),
            http_host=os.getenv("MCP_HTTP_HOST", "0.0.0.0"),
            http_port=http_port,
            http_auth_token=os.getenv("MCP_HTTP_AUTH_TOKEN"),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
            # Task queue configuration
            max_concurrent=max_concurrent,
            task_timeout=task_timeout,
            retry_limit=retry_limit,
            cleanup_days=cleanup_days,
            db_path=os.getenv("MINERU_DB_PATH", "output/tasks.db"),
            output_root=os.getenv("MINERU_OUTPUT_ROOT", "output"),
        )
    
    def is_http_mode(self) -> bool:
        """Check if server is running in HTTP mode."""
        return self.server_mode.lower() == "http"
    
    def is_stdio_mode(self) -> bool:
        """Check if server is running in stdio mode."""
        return self.server_mode.lower() == "stdio"
    
    def get_vlm_server_url(self) -> Optional[str]:
        """Get VLM server URL for http-client backends.
        
        Returns the VLM base URL if configured, otherwise None.
        """
        return self.vlm_base_url


# Global config instance
_config: Optional[MCPConfig] = None


def get_config() -> MCPConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = MCPConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
