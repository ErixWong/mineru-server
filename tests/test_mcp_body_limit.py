import pytest

from mineru_mcp.app import _resolve_max_request_body_size


def test_max_request_body_size_defaults_to_200mb(monkeypatch):
    monkeypatch.delenv("MINERU_MAX_REQUEST_BODY_SIZE", raising=False)

    assert _resolve_max_request_body_size() == 200 * 1024 * 1024


def test_max_request_body_size_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MINERU_MAX_REQUEST_BODY_SIZE", "123456789")

    assert _resolve_max_request_body_size() == 123456789


@pytest.mark.parametrize("invalid_value", ["not-an-integer", "0", "-1"])
def test_invalid_max_request_body_size_falls_back_to_default(
    monkeypatch, invalid_value
):
    monkeypatch.setenv("MINERU_MAX_REQUEST_BODY_SIZE", invalid_value)

    assert _resolve_max_request_body_size() == 200 * 1024 * 1024
