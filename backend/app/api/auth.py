"""Sign-in and the signed-in user's own account."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import LoginRequest, PasswordChange, TokenOut, UserOut
from app.services import audit, users

from .deps import client_ip, current_user
from .presenters import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """Exchanges username and password for an access token."""
    try:
        user = users.authenticate(db, body.username, body.password)
    except Exception:
        audit.record(db, None, "auth.login_failed", detail=f"username={body.username[:80]}", ip=client_ip(request))
        db.commit()
        raise
    audit.record(db, user, "auth.login", entity_type="user", entity_id=user.id, ip=client_ip(request))
    db.commit()
    return TokenOut(access_token=create_access_token(user.username), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    """The signed-in user."""
    return user_out(user)


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChange, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """Changes the signed-in user's own password."""
    users.change_password(db, user, body.current_password, body.new_password)
    audit.record(db, user, "auth.change_password", entity_type="user", entity_id=user.id, ip=client_ip(request))
    db.commit()
