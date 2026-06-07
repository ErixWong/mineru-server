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

    with pytest.raises(RuntimeError, match=r"Install 'mineru\[pipeline\]' or 'mineru\[core\]'"):
        mineru_adapter.require_mineru("hybrid-http-client")


def test_backend_dependency_help_recommends_http_client_for_hybrid():
    help_info = mineru_adapter.build_backend_dependency_help("hybrid-http-client")

    assert help_info["backend"] == "hybrid-http-client"
    assert help_info["fallback_backend"] == "vlm-http-client"
    assert "mineru[pipeline]" in help_info["install_hint"]


def test_backend_dependency_help_for_pipeline_is_specific():
    help_info = mineru_adapter.build_backend_dependency_help("pipeline")

    assert help_info["backend"] == "pipeline"
    assert help_info["fallback_backend"] is None
    assert help_info["install_hint"] == "Install 'mineru[pipeline]'."


def test_app_reload_does_not_mutate_sys_path():
    app_module = importlib.import_module("mineru_mcp.app")
    before = list(sys.path)

    importlib.reload(app_module)

    assert sys.path == before


def test_dockerfile_pins_mineru_ref():
    dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile"
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

    assert "ARG MINERU_REF=mineru-3.1.15-released" in dockerfile_text
    assert "--branch ${MINERU_REF}" in dockerfile_text
    assert "--branch master https://github.com/opendatalab/MinerU.git" not in dockerfile_text
