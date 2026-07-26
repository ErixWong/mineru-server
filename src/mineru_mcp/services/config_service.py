"""System configuration service.

将 `.env` 作为启动默认值，再用数据库中的 system_settings / system_secrets
覆盖可运营配置。根加密密钥仍来自环境变量，不写入数据库。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Optional

from loguru import logger

from mineru_mcp.caller_key_crypto import (
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)
from mineru_mcp.config import (
    DEFAULT_BACKEND,
    DEFAULT_POSTPROCESS_CONTEXT_SIZE,
    MCPConfig,
    VALID_BACKENDS,
)
from mineru_mcp.task_queue.database import TaskDatabase


SETTING_ENV_NAMES = {
    "default_backend": "MINERU_DEFAULT_BACKEND",
    "vlm_base_url": "MINERU_VL_SERVER",
    "vlm_model": "MINERU_VL_MODEL_NAME",
    "vlm_max_concurrency": "MINERU_VLM_MAX_CONCURRENCY",
    "title_base_url": "MINERU_TITLE_BASE_URL",
    "title_model": "MINERU_TITLE_MODEL",
    "postprocess_context_size": "MINERU_POSTPROCESS_CONTEXT_SIZE",
    "postprocess_max_concurrent": "MINERU_POSTPROCESS_MAX_CONCURRENT",
    "max_concurrent": "MINERU_MAX_CONCURRENT",
    "task_timeout": "MINERU_TASK_TIMEOUT",
    "retry_limit": "MINERU_RETRY_LIMIT",
    "cleanup_days": "MINERU_CLEANUP_DAYS",
}

SECRET_ENV_NAMES = {
    "vlm_api_key": "MINERU_VL_API_KEY",
    "title_api_key": "MINERU_TITLE_API_KEY",
}

EDITABLE_SETTING_KEYS = set(SETTING_ENV_NAMES)
EDITABLE_SECRET_KEYS = set(SECRET_ENV_NAMES)


def _clean_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _parse_positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _parse_default_backend(value: Any) -> str:
    backend = _clean_optional_string(value) or DEFAULT_BACKEND
    return backend if backend in VALID_BACKENDS else DEFAULT_BACKEND


SETTING_PARSERS: dict[str, Callable[[Any, MCPConfig], Any]] = {
    "default_backend": lambda value, _config: _parse_default_backend(value),
    "vlm_base_url": lambda value, _config: _clean_optional_string(value),
    "vlm_model": lambda value, _config: _clean_optional_string(value),
    "vlm_max_concurrency": lambda value, config: _parse_int(value, config.vlm_max_concurrency, 1, 100),
    "title_base_url": lambda value, _config: _clean_optional_string(value),
    "title_model": lambda value, _config: _clean_optional_string(value),
    "postprocess_context_size": lambda value, _config: _parse_positive_int(
        value,
        DEFAULT_POSTPROCESS_CONTEXT_SIZE,
        4096,
    ),
    "postprocess_max_concurrent": lambda value, config: _parse_int(
        value,
        config.postprocess_max_concurrent,
        1,
        32,
    ),
    "max_concurrent": lambda value, config: _parse_int(value, config.max_concurrent, 1, 100),
    "task_timeout": lambda value, config: _parse_positive_int(value, config.task_timeout, 1),
    "retry_limit": lambda value, config: _parse_int(value, config.retry_limit, 0, 100),
    "cleanup_days": lambda value, config: _parse_positive_int(value, config.cleanup_days, 1),
}


class ConfigService:
    """Read and update runtime configuration stored in SQLite."""

    def __init__(self, db_path: str, master_key: Optional[str] = None):
        self.db = TaskDatabase(db_path=db_path)
        self.master_key = (master_key or "").strip() or None

    def load_effective_config(self, bootstrap: MCPConfig) -> MCPConfig:
        """Return bootstrap config with database overrides applied."""
        settings = self.db.list_system_settings()
        secrets = self.db.list_system_secrets(include_ciphertext=True)
        overrides: dict[str, Any] = {}

        for key, row in settings.items():
            parser = SETTING_PARSERS.get(key)
            if parser is None:
                continue
            overrides[key] = parser(row.get("value"), bootstrap)

        for key, row in secrets.items():
            if key not in EDITABLE_SECRET_KEYS:
                continue
            ciphertext = row.get("secret_encrypted")
            if not ciphertext:
                continue
            if not self.master_key:
                raise RuntimeError(f"{SECRET_ENV_NAMES[key]} is stored in database but no master key is configured")
            overrides[key] = decrypt_api_key(ciphertext, self.master_key)

        if not overrides:
            return bootstrap
        return replace(bootstrap, **overrides)

    def get_runtime_payload(self, bootstrap: MCPConfig, effective: MCPConfig) -> dict[str, Any]:
        """Return Admin API-safe settings payload."""
        settings = self.db.list_system_settings()
        secret_meta = self.db.list_system_secrets(include_ciphertext=False)

        config_payload = {
            "default_backend": effective.default_backend,
            "vlm_base_url": effective.vlm_base_url or "",
            "vlm_model": effective.vlm_model or "",
            "vlm_max_concurrency": effective.vlm_max_concurrency,
            "title_base_url": effective.title_base_url or "",
            "title_model": effective.title_model or "",
            "postprocess_context_size": effective.postprocess_context_size,
            "postprocess_max_concurrent": effective.postprocess_max_concurrent,
            "max_concurrent": effective.max_concurrent,
            "task_timeout": effective.task_timeout,
            "retry_limit": effective.retry_limit,
            "cleanup_days": effective.cleanup_days,
        }

        sources = {
            key: "database" if key in settings else "environment"
            for key in SETTING_ENV_NAMES
        }
        secrets = {
            key: self._secret_payload(key, secret_meta.get(key), bootstrap)
            for key in SECRET_ENV_NAMES
        }

        return {
            "config": config_payload,
            "sources": sources,
            "secrets": secrets,
            "valid_backends": VALID_BACKENDS,
            "restart_required_keys": [
                "max_concurrent",
                "postprocess_max_concurrent",
                "vlm_max_concurrency",
            ],
        }

    def update_runtime_settings(
        self,
        *,
        settings: dict[str, Any],
        secrets: dict[str, Optional[str]],
        updated_by: str,
    ) -> None:
        """Persist validated settings and optional secret replacements."""
        now = datetime.now().isoformat()
        for key, value in settings.items():
            if key not in EDITABLE_SETTING_KEYS:
                raise ValueError(f"Unsupported setting: {key}")
            parser = SETTING_PARSERS[key]
            parsed_value = parser(value, self._bootstrap_for_validation())
            if parsed_value is None:
                self.db.delete_system_setting(key)
            else:
                self.db.set_system_setting(
                    key=key,
                    value=str(parsed_value),
                    value_type="int" if isinstance(parsed_value, int) else "string",
                    updated_by=updated_by,
                    updated_at=now,
                )

        for key, value in secrets.items():
            if key not in EDITABLE_SECRET_KEYS:
                raise ValueError(f"Unsupported secret: {key}")
            secret_value = (value or "").strip()
            if not secret_value:
                self.db.delete_system_secret(key)
                continue
            if not self.master_key:
                raise RuntimeError("MINERU_CALLER_KEY_MASTER_KEY is required to store system secrets")
            encrypted = encrypt_api_key(secret_value, self.master_key)
            prefix, suffix = mask_api_key(secret_value, prefix_len=6, suffix_len=4)
            self.db.set_system_secret(
                key=key,
                secret_encrypted=encrypted.ciphertext,
                secret_key_id=encrypted.key_id,
                secret_prefix=prefix,
                secret_suffix=suffix,
                updated_by=updated_by,
                updated_at=now,
            )

    def _bootstrap_for_validation(self) -> MCPConfig:
        from mineru_mcp.config import MCPConfig

        return MCPConfig.from_env()

    @staticmethod
    def _secret_payload(key: str, row: Optional[dict[str, Any]], bootstrap: MCPConfig) -> dict[str, Any]:
        env_value = getattr(bootstrap, key)
        if row:
            return {
                "configured": True,
                "source": "database",
                "prefix": row.get("secret_prefix") or "",
                "suffix": row.get("secret_suffix") or "",
                "key_id": row.get("secret_key_id") or "",
                "updated_at": row.get("updated_at"),
            }
        if env_value:
            prefix, suffix = mask_api_key(env_value, prefix_len=6, suffix_len=4)
            return {
                "configured": True,
                "source": "environment",
                "prefix": prefix,
                "suffix": suffix,
                "key_id": "",
                "updated_at": None,
            }
        return {
            "configured": False,
            "source": "none",
            "prefix": "",
            "suffix": "",
            "key_id": "",
            "updated_at": None,
        }


def load_effective_config(bootstrap: MCPConfig) -> MCPConfig:
    """Convenience wrapper used by get_config()."""
    try:
        service = ConfigService(bootstrap.db_path, bootstrap.caller_key_master_key)
        return service.load_effective_config(bootstrap)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to load database configuration overrides: {exc}")
        return bootstrap
