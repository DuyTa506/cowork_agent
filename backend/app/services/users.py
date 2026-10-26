"""User accounts: creation, sign-in, password changes, administration."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config
from app.core.errors import Conflict, NotFound, Unauthorized, ValidationFailed
from app.core.security import hash_password, verify_password
from app.models import ROLES, User

from . import organization

MIN_PASSWORD = 8


def _check_password(password: str) -> None:
    """Minimum password policy: length only. Anything stricter is a decision for the deployment, not the code."""
    if len(password) < MIN_PASSWORD:
        raise ValidationFailed(f"Mật khẩu phải có ít nhất {MIN_PASSWORD} ký tự.")


def _check_profile(username: str, role: str, unit_id: str) -> None:
    """Validates the fields common to creating and editing a user."""
    if not username or len(username) > 80 or username != username.strip() or " " in username:
        raise ValidationFailed("Tên đăng nhập không hợp lệ (không để trống, không có khoảng trắng).")
    if role not in ROLES:
        raise ValidationFailed(f"Vai trò phải là một trong: {', '.join(ROLES)}.")
    organization.require_unit(unit_id)


def get(db: Session, user_id: int) -> User:
    """The user with this id, or `NotFound`."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Không tìm thấy người dùng.")
    return user


def list_all(db: Session) -> list[User]:
    """Every account, by username."""
    return list(db.scalars(select(User).order_by(User.username)))


def create(db: Session, *, username: str, password: str, full_name: str, unit_id: str, role: str) -> User:
    """Creates an active account.

    Raises:
        ValidationFailed: bad username/role/unit or a weak password.
        Conflict: the username is taken (compared case-insensitively).
    """
    username = username.strip()
    _check_profile(username, role, unit_id)
    _check_password(password)
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.username) == username.lower())):
        raise Conflict("Tên đăng nhập đã tồn tại.")
    user = User(username=username, full_name=full_name.strip(), unit_id=unit_id, role=role, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def update(db: Session, user: User, *, full_name: str | None = None, unit_id: str | None = None, role: str | None = None,
           is_active: bool | None = None, password: str | None = None) -> list[str]:
    """Applies the given changes (None leaves a field alone) and returns the names of the fields that changed.

    Refuses to remove the last active administrator, so the system cannot lock itself out.
    """
    new_role = role if role is not None else user.role
    new_unit = unit_id if unit_id is not None else user.unit_id
    new_active = is_active if is_active is not None else user.is_active
    _check_profile(user.username, new_role, new_unit)
    if user.role == "admin" and user.is_active and (new_role != "admin" or not new_active):
        others = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True), User.id != user.id))
        if not others:
            raise Conflict("Phải còn ít nhất một quản trị viên đang hoạt động.")
    changed = []
    for name, value in (("full_name", full_name.strip() if full_name is not None else None), ("unit_id", unit_id), ("role", role),
                        ("is_active", is_active)):
        if value is not None and getattr(user, name) != value:
            setattr(user, name, value)
            changed.append(name)
    if password is not None:
        _check_password(password)
        user.password_hash = hash_password(password)
        changed.append("password")
    return changed


def authenticate(db: Session, username: str, password: str) -> User:
    """The active user with these credentials, or `Unauthorized`. The error never says which half was wrong."""
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    # verify against a dummy hash for unknown users so response time does not reveal which usernames exist
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not (user and ok and user.is_active):
        raise Unauthorized("Sai tên đăng nhập hoặc mật khẩu.")
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    """Changes the user's own password after checking the current one."""
    if not verify_password(current, user.password_hash):
        raise ValidationFailed("Mật khẩu hiện tại không đúng.")
    _check_password(new)
    user.password_hash = hash_password(new)


def ensure_admin(db: Session) -> User | None:
    """Creates the bootstrap administrator from the environment when no account exists yet; returns it, or None otherwise."""
    if db.scalar(select(func.count()).select_from(User)):
        return None
    user = create(db, username=config.ADMIN_USERNAME, password=config.ADMIN_PASSWORD, full_name=config.ADMIN_FULL_NAME,
                  unit_id=config.ADMIN_UNIT_ID, role="admin")
    db.commit()
    return user


_DUMMY_HASH = hash_password("not-a-real-password")
