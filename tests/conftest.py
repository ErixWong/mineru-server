import pytest


TEST_CALLER_KEY_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


@pytest.fixture(autouse=True)
def _default_caller_key_master_key(monkeypatch):
    """Keep tests off production secrets while caller key encryption is mandatory."""
    monkeypatch.setenv("MINERU_CALLER_KEY_MASTER_KEY", TEST_CALLER_KEY_MASTER_KEY)
