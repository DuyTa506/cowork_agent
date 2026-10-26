"""Format-check payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CheckOptions(BaseModel):
    """What the screen offers before a file is chosen."""

    profiles: list[dict[str, Any]]
    default_profile: str
    default_spell: bool
    accept: list[str]
    max_mb: int
    retention_hours: int


class CheckOut(BaseModel):
    """A checked file. `result` is doccheck's display payload (see docs/FORMAT_CHECK_API.md): facts, counts, `banner`
    (findings without a location), `paras` (each with `msgs` and spelling `marks`), selectable `items` and `manual` notes."""

    id: str
    name: str
    size: int
    kind: str
    can_fix: bool
    profile: str
    spell: bool
    fixed: bool
    counts: dict[str, int]
    created_at: datetime
    expires_at: datetime
    result: dict[str, Any]


class CheckRequest(BaseModel):
    """Options for checking again."""

    profile: str | None = None
    spell: bool | None = None


class FixRequest(BaseModel):
    """Edits to apply: ids from `result.items[].id`. `track` leaves Word tracked changes, `apply` writes the new format directly."""

    ids: list[str] = Field(min_length=1)
    mode: str = "track"


class FixOut(BaseModel):
    """Outcome of applying edits."""

    applied: list[str]
    failed: list[dict[str, str]]
    after: dict[str, int]


class SaveRequest(BaseModel):
    """Saving a checked file into the document store."""

    which: str = "fixed"
    declared_secret: bool = False
