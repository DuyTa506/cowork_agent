"""Authentication and user administration."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Sign-in form."""

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    """A user changing their own password."""

    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class UserOut(BaseModel):
    """An account as shown to clients (never includes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    unit_id: str
    unit_name: str = ""
    role: str
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    """Result of a successful sign-in."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    """Administrator creating an account."""

    username: str = Field(max_length=80)
    password: str = Field(max_length=256)
    full_name: str = Field(default="", max_length=160)
    unit_id: str = Field(max_length=64)
    role: str = "staff"


class UserUpdate(BaseModel):
    """Administrator editing an account; omitted fields are left unchanged."""

    full_name: str | None = Field(default=None, max_length=160)
    unit_id: str | None = Field(default=None, max_length=64)
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)
