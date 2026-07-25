import pytest

from mineru_mcp.caller_key_crypto import (
    CallerKeyCryptoError,
    decrypt_api_key,
    encrypt_api_key,
    generate_master_key,
    get_api_key_digest,
    get_master_key_id,
    mask_api_key,
    validate_master_key,
)
from mineru_mcp.config import require_caller_key_master_key, reset_config


TEST_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def test_encrypt_api_key_uses_random_ciphertext_and_decrypts():
    first = encrypt_api_key("caller-secret-token", TEST_MASTER_KEY)
    second = encrypt_api_key("caller-secret-token", TEST_MASTER_KEY)

    assert first.ciphertext != second.ciphertext
    assert decrypt_api_key(first.ciphertext, TEST_MASTER_KEY) == "caller-secret-token"
    assert decrypt_api_key(second.ciphertext, TEST_MASTER_KEY) == "caller-secret-token"
    assert first.digest == second.digest
    assert first.key_id == second.key_id
    assert first.prefix == "caller-s"
    assert first.suffix == "oken"


def test_wrong_master_key_cannot_decrypt_ciphertext():
    other_master_key = generate_master_key()
    encrypted = encrypt_api_key("caller-secret-token", TEST_MASTER_KEY)

    with pytest.raises(CallerKeyCryptoError, match="cannot be decrypted"):
        decrypt_api_key(encrypted.ciphertext, other_master_key)


def test_corrupt_ciphertext_is_rejected_without_echoing_ciphertext():
    with pytest.raises(CallerKeyCryptoError) as exc_info:
        decrypt_api_key("not-a-valid-token", TEST_MASTER_KEY)

    assert "not-a-valid-token" not in str(exc_info.value)


def test_invalid_master_key_is_rejected_without_echoing_key():
    bad_key = "not-a-valid-fernet-key"

    with pytest.raises(CallerKeyCryptoError) as exc_info:
        validate_master_key(bad_key)

    assert bad_key not in str(exc_info.value)


def test_digest_and_key_id_are_stable_and_do_not_expose_api_key():
    digest = get_api_key_digest("caller-secret-token", TEST_MASTER_KEY)
    repeated_digest = get_api_key_digest("caller-secret-token", TEST_MASTER_KEY)
    different_digest = get_api_key_digest("another-token", TEST_MASTER_KEY)
    key_id = get_master_key_id(TEST_MASTER_KEY)

    assert digest == repeated_digest
    assert digest != different_digest
    assert digest.startswith("ckd_")
    assert key_id.startswith("mk_")
    assert "caller-secret-token" not in digest
    assert TEST_MASTER_KEY not in key_id


def test_mask_api_key_returns_display_only_edges():
    assert mask_api_key("caller-secret-token") == ("caller-s", "oken")


def test_require_caller_key_master_key_validates_env(monkeypatch):
    monkeypatch.setenv("MINERU_CALLER_KEY_MASTER_KEY", TEST_MASTER_KEY)
    reset_config()

    assert require_caller_key_master_key() == TEST_MASTER_KEY


def test_require_caller_key_master_key_rejects_missing_or_invalid_env(monkeypatch):
    monkeypatch.delenv("MINERU_CALLER_KEY_MASTER_KEY", raising=False)
    reset_config()

    with pytest.raises(RuntimeError, match="MINERU_CALLER_KEY_MASTER_KEY is required"):
        require_caller_key_master_key()

    monkeypatch.setenv("MINERU_CALLER_KEY_MASTER_KEY", "invalid-master-key")
    reset_config()

    with pytest.raises(RuntimeError, match="MINERU_CALLER_KEY_MASTER_KEY is invalid"):
        require_caller_key_master_key()
