"""Spelling-check payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SpellOptions(BaseModel):
    """What the screen offers before anything is checked."""

    accept: list[str]
    max_mb: int
    max_chars: int
    retention_hours: int


class SpellOut(BaseModel):
    """A checked file or text. `result` has the shape of a format-check payload with spelling only (see docs/SPELLCHECK_API.md):
    `paras` with `marks`, selectable `items` (kind ``spelling``), hand-fix `manual` notes, `counts`, and `ignored` (findings hidden
    by the ignore list)."""

    id: str
    name: str
    size: int
    kind: str
    can_fix: bool
    fixed: bool
    counts: dict[str, int]
    ignore: list[str]
    created_at: datetime
    expires_at: datetime
    result: dict[str, Any]


class TextRequest(BaseModel):
    """Pasted text to check (lines separated by line breaks)."""

    text: str
    markdown: bool = False


class IgnoreRequest(BaseModel):
    """The complete ignore list: words (case-insensitive) the screen must not report in this session."""

    words: list[str] = Field(max_length=500)


class SpellFixRequest(BaseModel):
    """Edits to apply: ids from `result.items[].id`. `track` leaves Word tracked changes, `apply` writes the text directly."""

    ids: list[str] = Field(min_length=1)
    mode: str = "track"


class SpellFixOut(BaseModel):
    """Outcome of applying edits; `after.spelling` is what a new check of the corrected copy still finds."""

    applied: list[str]
    failed: list[dict[str, str]]
    after: dict[str, int]
    text: str | None = None
