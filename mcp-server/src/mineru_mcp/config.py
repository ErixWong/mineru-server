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

DEFAULT_POSTPROCESS_CONTEXT_SIZE = 128 * 1024


@dataclass
class MCPConfig:
    """MCP Server configuration from environment variables."""
    
    # MinerU Backend configuration
    default_backend: str  # Default parsing backend
    
    # VLM API configuration (for http-client backends)
    vlm_base_url: Optional[str]  # VLM API base URL (e.g., https://api.openai.com/v1)
    vlm_api_key: Optional[str]  # VLM API key
    vlm_model: Optional[str]  # VLM model name
    vlm_max_concurrency: int
    
    # Title optimization LLM configuration (optional)
    title_api_key: Optional[str]
    title_base_url: Optional[str]
    title_model: Optional[str]
    postprocess_context_size: int
    postprocess_max_concurrent: int
    
    # MCP Server configuration
    server_name: str
    server_mode: str  # "stdio" or "http"
    http_host: str
    http_port: int
    
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
            http_port = int(os.getenv("MCP_HTTP_PORT", "8002") or "8002")
        except ValueError:
            http_port = 8002
        
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
            vlm_max_concurrency = int(os.getenv("MINERU_VLM_MAX_CONCURRENCY", "2") or "2")
        except ValueError:
            vlm_max_concurrency = 2
        
        try:
            retry_limit = int(os.getenv("MINERU_RETRY_LIMIT", "3") or "3")
        except ValueError:
            retry_limit = 3
        
        try:
            cleanup_days = int(os.getenv("MINERU_CLEANUP_DAYS", "300") or "300")
        except ValueError:
            cleanup_days = 300

        try:
            postprocess_context_size = int(
                os.getenv("MINERU_POSTPROCESS_CONTEXT_SIZE", str(DEFAULT_POSTPROCESS_CONTEXT_SIZE))
                or str(DEFAULT_POSTPROCESS_CONTEXT_SIZE)
            )
            postprocess_context_size = max(4096, postprocess_context_size)
        except ValueError:
            postprocess_context_size = DEFAULT_POSTPROCESS_CONTEXT_SIZE

        # 后处理 run 并发度独立于解析并发：LLM 调用是 IO 密集，
        # 不应与 GPU 解析抢占同一槽位。
        try:
            postprocess_max_concurrent = int(os.getenv("MINERU_POSTPROCESS_MAX_CONCURRENT", "2") or "2")
            postprocess_max_concurrent = max(1, min(32, postprocess_max_concurrent))
        except ValueError:
            postprocess_max_concurrent = 2
        
        return cls(
            default_backend=default_backend,
            # VLM API configuration
            vlm_base_url=os.getenv("MINERU_VL_SERVER"),
            vlm_api_key=os.getenv("MINERU_VL_API_KEY"),
            vlm_model=os.getenv("MINERU_VL_MODEL_NAME"),
            vlm_max_concurrency=vlm_max_concurrency,
            # Title optimization LLM configuration
            title_api_key=os.getenv("MINERU_TITLE_API_KEY"),
            title_base_url=os.getenv("MINERU_TITLE_BASE_URL"),
            title_model=os.getenv("MINERU_TITLE_MODEL"),
            postprocess_context_size=postprocess_context_size,
            postprocess_max_concurrent=postprocess_max_concurrent,
            # MCP Server configuration
            server_name=os.getenv("MCP_SERVER_NAME", "MinerU MCP Server"),
            server_mode=os.getenv("MCP_SERVER_MODE", "stdio"),
            http_host=os.getenv("MCP_HTTP_HOST", "0.0.0.0"),
            http_port=http_port,
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

    def get_vlm_api_key(self) -> Optional[str]:
        """Get VLM API key for http-client backends."""
        return self.vlm_api_key

    def get_vlm_model(self) -> Optional[str]:
        """Get VLM model name for http-client backends."""
        return self.vlm_model


# Global config instance
_config: Optional[MCPConfig] = None


def _resolve_tools_config_path() -> Path:
    """Resolve MinerU tools config path using upstream semantics."""
    config_name = os.getenv("MINERU_TOOLS_CONFIG_JSON", "mineru.json")
    config_path = Path(config_name)
    if config_path.is_absolute():
        return config_path
    return Path.home() / config_path


def sync_title_aided_config() -> None:
    """Sync MINERU_TITLE_* env vars into upstream llm-aided-config.title_aided."""
    title_api_key = os.getenv("MINERU_TITLE_API_KEY")
    title_base_url = os.getenv("MINERU_TITLE_BASE_URL")
    title_model = os.getenv("MINERU_TITLE_MODEL")

    provided = [
        value for value in (title_api_key, title_base_url, title_model)
        if value is not None and value != ""
    ]
    if not provided:
        return

    if len(provided) != 3:
        logger.warning(
            "MINERU_TITLE_* variables are partially configured; skip syncing title_aided config."
        )
        return

    config_path = _resolve_tools_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_data: dict = {}
    if config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid MinerU config JSON at {config_path}, recreating title_aided config block")
            config_data = {}

    llm_aided_config = config_data.get("llm-aided-config")
    if not isinstance(llm_aided_config, dict):
        llm_aided_config = {}
        config_data["llm-aided-config"] = llm_aided_config

    title_aided_config = llm_aided_config.get("title_aided")
    if not isinstance(title_aided_config, dict):
        title_aided_config = {}
        llm_aided_config["title_aided"] = title_aided_config

    title_aided_config.update(
        {
            "api_key": title_api_key,
            "base_url": title_base_url,
            "model": title_model,
            "enable": True,
        }
    )
    title_aided_config.setdefault("enable_thinking", False)
    config_data.setdefault("config_version", "1.3.1")

    config_path.write_text(
        json.dumps(config_data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def get_config() -> MCPConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        sync_title_aided_config()
        _config = MCPConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
