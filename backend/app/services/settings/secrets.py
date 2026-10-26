"""Encryption of secret setting values (API keys) at rest."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core import config

_PREFIX = "enc:"


def _cipher() -> Fernet:
    """Fernet keyed by `SETTINGS_KEY`, or derived from `JWT_SECRET` when it is not set (documented fallback for small setups)."""
    key = config.SETTINGS_KEY or base64.urlsafe_b64encode(hashlib.sha256(("qk3-settings|" + config.JWT_SECRET).encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    """Encrypts `value` for storage; an empty value stays empty (it means "no secret")."""
    return _PREFIX + _cipher().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    """Reverses `encrypt`. A value that is not encrypted is returned as is; one that cannot be decrypted (the key changed)
    is treated as unset instead of failing every request that reads settings."""
    if not value.startswith(_PREFIX):
        return value
    try:
        return _cipher().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""
