"""Password hashing and access tokens. Framework-free: the FastAPI dependencies that use these live in `app.api.deps`."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt

from . import config
from .errors import Unauthorized

_ALGORITHM = "HS256"
_HASH_NAME = "pbkdf2_sha256"
_HASH_ROUNDS = 310_000  # OWASP guidance for PBKDF2-HMAC-SHA256


def hash_password(password: str) -> str:
    """Returns `pbkdf2_sha256$rounds$salt$digest` with a fresh random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ROUNDS)
    return "$".join((_HASH_NAME, str(_HASH_ROUNDS), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of a password against a hash made by `hash_password`; malformed hashes simply fail."""
    try:
        name, rounds, salt64, expected64 = encoded.split("$", 3)
        if name != _HASH_NAME:
            return False
        salt = base64.urlsafe_b64decode(salt64.encode())
        expected = base64.urlsafe_b64decode(expected64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(username: str) -> str:
    """Signed token naming the user; it expires after `JWT_EXPIRE_MINUTES`."""
    now = int(time.time())
    claims = {"sub": username, "iat": now, "exp": now + config.JWT_EXPIRE_MINUTES * 60}
    return jwt.encode(claims, config.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verifies signature and expiry and returns the claims; raises `Unauthorized` otherwise."""
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError as exc:
        raise Unauthorized("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.") from exc
