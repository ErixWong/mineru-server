"""Caller API key encryption helpers.

完整 caller key、主密钥、密文和摘要都属于敏感数据；本模块只返回给
调用方显式要求的值，不写日志，也不把敏感值放进异常消息。
"""

import base64
import hashlib
import hmac
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


class CallerKeyCryptoError(ValueError):
    """Raised when caller key crypto input cannot be processed safely."""


@dataclass(frozen=True)
class EncryptedCallerKey:
    """Encrypted caller key material ready for database storage."""

    ciphertext: str
    key_id: str
    digest: str
    prefix: str
    suffix: str


def generate_master_key() -> str:
    """Generate a new Fernet-compatible master key for configuration."""
    return Fernet.generate_key().decode("ascii")


def validate_master_key(master_key: str) -> str:
    """Validate and normalize a Fernet master key.

    Args:
        master_key: Fernet key from MINERU_CALLER_KEY_MASTER_KEY.

    Returns:
        The stripped key string.

    Raises:
        CallerKeyCryptoError: If the key is missing or invalid.
    """
    key = (master_key or "").strip()
    if not key:
        raise CallerKeyCryptoError("caller key master key is required")

    try:
        fernet = Fernet(key.encode("ascii"))
        probe = fernet.encrypt(b"probe")
        if fernet.decrypt(probe) != b"probe":
            raise CallerKeyCryptoError("caller key master key is invalid")
    except (ValueError, TypeError, InvalidToken) as exc:
        raise CallerKeyCryptoError("caller key master key is invalid") from exc

    return key


def _decoded_master_key(master_key: str) -> bytes:
    key = validate_master_key(master_key)
    try:
        return base64.urlsafe_b64decode(key.encode("ascii"))
    except ValueError as exc:
        raise CallerKeyCryptoError("caller key master key is invalid") from exc


def get_master_key_id(master_key: str) -> str:
    """Return a short non-secret identifier for the configured master key."""
    key_bytes = _decoded_master_key(master_key)
    return "mk_" + hashlib.sha256(key_bytes).hexdigest()[:16]


def get_api_key_digest(api_key: str, master_key: str) -> str:
    """Return a stable HMAC digest for indexed caller key lookup."""
    key_bytes = _decoded_master_key(master_key)
    token = _require_api_key(api_key)
    digest = hmac.new(key_bytes, token.encode("utf-8"), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return "ckd_" + encoded


def mask_api_key(api_key: str, prefix_len: int = 8, suffix_len: int = 4) -> tuple[str, str]:
    """Return display-only prefix and suffix for a caller key."""
    token = _require_api_key(api_key)
    return token[:prefix_len], token[-suffix_len:]


def encrypt_api_key(api_key: str, master_key: str) -> EncryptedCallerKey:
    """Encrypt a caller API key and compute its lookup metadata."""
    key = validate_master_key(master_key)
    token = _require_api_key(api_key)
    ciphertext = Fernet(key.encode("ascii")).encrypt(token.encode("utf-8")).decode("ascii")
    prefix, suffix = mask_api_key(token)
    return EncryptedCallerKey(
        ciphertext=ciphertext,
        key_id=get_master_key_id(key),
        digest=get_api_key_digest(token, key),
        prefix=prefix,
        suffix=suffix,
    )


def decrypt_api_key(ciphertext: str, master_key: str) -> str:
    """Decrypt a stored caller API key ciphertext."""
    key = validate_master_key(master_key)
    encrypted = (ciphertext or "").strip()
    if not encrypted:
        raise CallerKeyCryptoError("caller key ciphertext is required")

    try:
        plaintext = Fernet(key.encode("ascii")).decrypt(encrypted.encode("ascii"))
    except (ValueError, TypeError, InvalidToken) as exc:
        raise CallerKeyCryptoError("caller key ciphertext cannot be decrypted") from exc

    return plaintext.decode("utf-8")


def _require_api_key(api_key: str) -> str:
    token = (api_key or "").strip()
    if not token:
        raise CallerKeyCryptoError("caller api key is required")
    return token
