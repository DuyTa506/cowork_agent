"""FastAPI dependencies shared by the routers."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.runtime import AgentPool
from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    """The signed-in, active user behind the bearer token."""
    if credentials is None:
        raise Unauthorized("Chưa đăng nhập.")
    username = decode_access_token(credentials.credentials)["sub"]
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        raise Unauthorized("Tài khoản không còn hiệu lực.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    """The signed-in user, who must be an administrator."""
    if user.role != "admin":
        raise Forbidden("Chức năng này chỉ dành cho quản trị viên.")
    return user


def attachment(filename: str) -> str:
    """``Content-Disposition`` of a download. A header value is Latin-1, so a Vietnamese file name goes in RFC 5987 form (what
    `FileResponse` sends); the plain `filename` is an ASCII fallback for old clients."""
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "") or "tai-xuong"
    return f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{quote(filename)}"


def client_ip(request: Request) -> str:
    """Caller address for the audit trail (behind the proxy this is the forwarded address, see `--proxy-headers`)."""
    return request.client.host if request.client else ""


def agent_pool(request: Request) -> AgentPool:
    """The pool of per-conversation agent runtimes (created at start-up)."""
    return request.app.state.agent_pool


def session_factory(request: Request):
    """Opens database sessions outside a request (a turn keeps running after the response is gone)."""
    return request.app.state.session_factory
