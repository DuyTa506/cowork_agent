"""Document store payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    """A document as listed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    title: str
    subject: str
    document_type: str
    document_number: str
    symbol: str
    issuer: str
    issued_date: str
    signer: str
    unit_id: str
    unit_name: str = ""
    level: str
    state: str
    state_detail: str
    file_size: int
    chunk_count: int
    uploaded_by_id: int
    uploaded_by_name: str = ""
    uploaded_at: datetime
    updated_at: datetime
    tags: list[str] = []


class DocumentDetail(DocumentOut):
    """A single document with its processing history."""

    steps: list[dict[str, Any]]
    warnings: list[str]
    secret_reasons: list[str] = []
    can_manage: bool = False
    manual_tags: list[str] = []  # the part of `tags` a person set (editable); the rest is computed


class ScanBlock(BaseModel):
    """A block of a scanned page: kind, position (x0, y0, x1, y1 on a 0-1000 scale of the page), text, and the viewer paragraphs written from it."""

    page: int
    label: str
    box: list[int]
    text: str
    pi: list[int] | None = None


class ScanOut(BaseModel):
    pages: int
    blocks: list[ScanBlock]


class DocumentPage(BaseModel):
    """One page of a listing plus the per-state totals for the filter chips."""

    items: list[DocumentOut]
    total: int
    states: dict[str, int]


class UploadItem(BaseModel):
    """Outcome for one file of a (possibly multi-file) upload; a failing file does not stop the others."""

    name: str
    document: DocumentOut | None = None
    error: str = ""
    code: str = ""
    existing_id: int | None = None


class UploadResult(BaseModel):
    """Per-file outcomes of an upload request."""

    items: list[UploadItem]


class MetadataUpdate(BaseModel):
    """Manual corrections of extracted metadata; omitted fields are unchanged."""

    title: str | None = None
    subject: str | None = None
    document_type: str | None = None
    document_number: str | None = None
    symbol: str | None = None
    issuer: str | None = None
    issued_date: str | None = None
    signer: str | None = None


class TagsUpdate(BaseModel):
    """The hand-made tags of a document (the whole list; computed tags are not affected)."""

    tags: list[str]


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    """Choices for the filter panel with the number of readable documents behind each."""

    units: list[FacetValue]  # value = unit id; documents directly in that unit (the screen adds up subtrees)
    types: list[FacetValue]
    years: list[FacetValue]
    tags: list[FacetValue]


class Paragraph(BaseModel):
    """One paragraph of the document viewer; `pi` is the source index that citations refer to."""

    pi: int
    text: str
    align: str = "left"
    bold: bool = False
    italic: bool = False
    table: int | None = None
    row: int | None = None
    col: int | None = None
