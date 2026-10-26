"""Assistant payloads: conversations, messages, attachments and the draft (canvas)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .documents import DocumentOut


class SessionCreate(BaseModel):
    """Start a conversation (title optional; it is taken from the first message otherwise)."""

    title: str = ""


class SessionRename(BaseModel):
    title: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    """One message. For the assistant, `content` carries the numbered citations ``[1]`` that `citations[].n` refers to."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    steps: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    status: str = "done"
    attachment_ids: list[int] = []
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: int
    state: str
    detail: str = ""
    title: str = ""
    document_type: str = ""
    chunk_count: int = 0


class DraftOut(BaseModel):
    """The conversation's draft as the canvas shows it (see docs/CHAT_API.md)."""

    id: int
    title: str
    version: int
    updated_at: datetime
    template: dict[str, Any]
    fields: dict[str, dict[str, Any]]
    blocks: list[dict[str, Any]]
    missing: list[str]
    style: dict[str, str]
    style_options: dict[str, Any]
    history: list[dict[str, Any]]
    unit_id: str = ""  # the drafting unit chosen on the canvas ("" = the author's unit)
    unit_name: str = ""


class SessionDetail(BaseModel):
    session: SessionOut
    messages: list[MessageOut]
    attachments: list[AttachmentOut]
    draft: DraftOut | None = None


class MessageIn(BaseModel):
    """A message to the assistant. `context` names the canvas block (and the selected text) the request is about."""

    text: str
    attachment_ids: list[int] = Field(default_factory=list)
    canvas: bool = False
    context: dict[str, str] | None = None


class BlockEdit(BaseModel):
    """New text of a block, or the new spec of a table block (``{"columns", "rows"}``, see app.drafting.tables)."""

    id: str
    text: str = ""
    table: dict[str, Any] | None = None


class BlockInsert(BaseModel):
    after: str | None = None
    kind: str = "para"
    text: str = ""
    table: dict[str, Any] | None = None


class StyleChoice(BaseModel):
    """The preset and detail level picked on the canvas (unknown values fall back to the defaults)."""

    preset: str = ""
    detail: str = ""


class DraftPatch(BaseModel):
    """The user's edits to the draft: fields by key, text of existing blocks, one insertion, deletions, the style choice, the
    drafting unit (an id within the user's own unit), and passages whose "figures changed" mark the user dismisses."""

    fields: dict[str, str] | None = None
    blocks: list[BlockEdit] | None = None
    insert: BlockInsert | None = None
    delete: list[str] | None = None
    style: StyleChoice | None = None
    unit_id: str | None = None
    reviewed: list[str] | None = None


class DraftCreate(BaseModel):
    """Open a draft by hand (the assistant normally does this)."""

    kind: str
    replace: bool = False
    unit: str = ""  # the drafting unit (id or name); the user's own when empty


class DraftSave(BaseModel):
    declared_secret: bool = False


class DraftCheckOut(BaseModel):
    counts: dict[str, int]
    findings: list[dict[str, Any]]
    checked_at: str
    style: dict[str, Any] = {}


class DraftSaved(BaseModel):
    document: DocumentOut
