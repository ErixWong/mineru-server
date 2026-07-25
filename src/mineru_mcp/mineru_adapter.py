"""MinerU integration adapter.

Centralizes all imports from the upstream MinerU package so the rest of the
codebase does not depend on MinerU's internal module layout directly.
"""

from pathlib import Path
from typing import Any

from loguru import logger


try:
    from mineru.cli.common import do_parse as _do_parse
    from mineru.cli.common import read_fn as _read_fn
    _MINERU_IMPORT_ERROR: ImportError | None = None
except ImportError as exc:
    _do_parse = None
    _read_fn = None
    _MINERU_IMPORT_ERROR = exc
    logger.warning(f"MinerU import failed: {exc}")


def is_mineru_available() -> bool:
    """Return whether the upstream MinerU dependency imported successfully."""
    return _MINERU_IMPORT_ERROR is None and _do_parse is not None and _read_fn is not None


def build_backend_dependency_help(backend: str | None) -> dict[str, str | None]:
    """Build backend-specific installation guidance.

    Keeps wording aligned with the upstream MinerU extras model.
    """
    normalized_backend = backend or "unknown"

    if normalized_backend.startswith("hybrid-"):
        return {
            "backend": normalized_backend,
            "message": (
                f"Backend '{normalized_backend}' requires local pipeline dependencies, "
                "including torch."
            ),
            "install_hint": "Install 'mineru[pipeline]' or 'mineru[core]'.",
            "fallback_backend": "vlm-http-client",
        }

    if normalized_backend == "pipeline":
        return {
            "backend": normalized_backend,
            "message": "Backend 'pipeline' requires local pipeline dependencies.",
            "install_hint": "Install 'mineru[pipeline]'.",
            "fallback_backend": None,
        }

    if normalized_backend.startswith("vlm-") and normalized_backend != "vlm-http-client":
        return {
            "backend": normalized_backend,
            "message": f"Backend '{normalized_backend}' requires local VLM runtime dependencies.",
            "install_hint": "Install 'mineru[vlm]' or 'mineru[core]'.",
            "fallback_backend": "vlm-http-client",
        }

    return {
        "backend": normalized_backend,
        "message": f"Backend '{normalized_backend}' requires the MinerU runtime to be installed.",
        "install_hint": "Install 'mineru' and ensure its runtime dependencies are available.",
        "fallback_backend": None,
    }


def format_backend_dependency_message(backend: str | None) -> str:
    """Format a backend-specific dependency error message."""
    help_info = build_backend_dependency_help(backend)
    parts = [str(help_info["message"]), str(help_info["install_hint"])]
    if help_info["fallback_backend"]:
        parts.append(
            f"If you want a lighter remote-only path, use '{help_info['fallback_backend']}' instead."
        )
    return " ".join(parts)


def require_mineru(backend: str | None = None) -> None:
    """Fail fast with an actionable error when MinerU is unavailable."""
    if not is_mineru_available():
        raise RuntimeError(format_backend_dependency_message(backend)) from _MINERU_IMPORT_ERROR


def read_file_bytes(path: Path) -> bytes:
    """Read bytes using MinerU's file helper."""
    require_mineru()
    return _read_fn(path)


def run_parse(**kwargs: Any) -> None:
    """Execute MinerU parsing through the upstream parse entry point."""
    require_mineru(kwargs.get("backend"))
    _do_parse(**kwargs)
