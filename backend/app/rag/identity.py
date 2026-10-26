"""Who the agent is acting for, carried as a short-lived signed token.

The backend starts one tool process per chat session and puts the token in its environment. The model can call the tools
but cannot change the environment of the process that serves them, so it cannot pick another unit or role.
"""
from __future__ import annotations
import os
import time
from dataclasses import dataclass

import jwt

from app.org import Principal

ENV_TOKEN = "QK3_SCOPE_TOKEN"
_ALG = "HS256"

class IdentityError(Exception):
    pass

@dataclass(frozen=True)
class Caller:
    """Who the tools act for: the principal (unit, role), the user, and the chat session the tools are serving ("" outside chat)."""

    principal: Principal
    user_id: int = 0
    session_id: str = ""


def issue(principal: Principal, secret: str, ttl_seconds: int = 3600, user: str = "", user_id: int = 0, session_id: str = "") -> str:
    """Signs a token for the tool process of one chat session."""
    now = int(time.time())
    return jwt.encode({"unit": principal.unit_id, "role": principal.role, "sub": user, "uid": user_id, "sid": session_id, "iat": now,
                       "exp": now + ttl_seconds, "aud": "qk3-tools"}, secret, algorithm=_ALG)


def verify_caller(token: str, secret: str) -> Caller:
    """The caller named by a token; raises `IdentityError` when it is forged, malformed or expired."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALG], audience="qk3-tools", options={"require": ["exp", "unit", "role"]})
    except jwt.PyJWTError as exc:
        raise IdentityError(f"Token không hợp lệ hoặc đã hết hạn: {exc}") from exc
    return Caller(Principal(claims["unit"], claims["role"]), int(claims.get("uid", 0)), str(claims.get("sid", "")))


def verify(token: str, secret: str) -> Principal:
    """Principal only (see `verify_caller`)."""
    return verify_caller(token, secret).principal


def caller_from_environment(secret: str) -> Caller:
    """The caller named by QK3_SCOPE_TOKEN in this process's environment."""
    token = os.environ.get(ENV_TOKEN, "")
    if not token:
        raise IdentityError(f"Thiếu {ENV_TOKEN}: công cụ không chạy khi không biết đang thay mặt ai.")
    return verify_caller(token, secret)


def from_environment(secret: str) -> Principal:
    """Principal named by QK3_SCOPE_TOKEN in this process's environment."""
    return caller_from_environment(secret).principal
