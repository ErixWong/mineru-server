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


def require_mineru() -> None:
    """Fail fast with an actionable error when MinerU is unavailable."""
    if not is_mineru_available():
        raise RuntimeError(
            "MinerU is required but not importable. Install the 'mineru' dependency "
            "declared in pyproject.toml and ensure its runtime dependencies are available."
        ) from _MINERU_IMPORT_ERROR


def read_file_bytes(path: Path) -> bytes:
    """Read bytes using MinerU's file helper."""
    require_mineru()
    return _read_fn(path)


def run_parse(**kwargs: Any) -> None:
    """Execute MinerU parsing through the upstream parse entry point."""
    require_mineru()
    _do_parse(**kwargs)
