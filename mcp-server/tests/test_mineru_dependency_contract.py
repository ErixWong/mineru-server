import importlib
import sys
import tomllib
from pathlib import Path

import pytest

from mineru_mcp import mineru_adapter


def test_pyproject_declares_mineru_dependency():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert any(dep.startswith("mineru>=") for dep in dependencies)


def test_require_mineru_reports_actionable_error(monkeypatch):
    monkeypatch.setattr(mineru_adapter, "_do_parse", None)
    monkeypatch.setattr(mineru_adapter, "_read_fn", None)
    monkeypatch.setattr(mineru_adapter, "_MINERU_IMPORT_ERROR", ImportError("missing mineru"))

    with pytest.raises(RuntimeError, match="Install the 'mineru' dependency"):
        mineru_adapter.require_mineru()


def test_app_reload_does_not_mutate_sys_path():
    app_module = importlib.import_module("mineru_mcp.app")
    before = list(sys.path)

    importlib.reload(app_module)

    assert sys.path == before
