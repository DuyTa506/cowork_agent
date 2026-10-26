"""Builds response models from ORM rows (adds the display names the database does not hold)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Document, User
from app.schemas.auth import UserOut
from app.schemas.documents import DocumentDetail, DocumentOut
from app.services import organization, tagging


def unit_name(unit_id: str) -> str:
    """Display name of a unit, or the id itself if it is no longer in the chart."""
    units = organization.tree().units
    return units[unit_id].name if unit_id in units else unit_id


def user_out(user: User) -> UserOut:
    """Account with its unit's display name."""
    out = UserOut.model_validate(user)
    out.unit_name = unit_name(user.unit_id)
    return out


def _uploader_names(db: Session, documents: list[Document]) -> dict[int, str]:
    """Display name of each uploader, fetched in one query."""
    ids = {d.uploaded_by_id for d in documents}
    rows = db.query(User.id, User.full_name, User.username).filter(User.id.in_(ids)).all() if ids else []
    return {row.id: row.full_name or row.username for row in rows}


def document_out(db: Session, documents: list[Document]) -> list[DocumentOut]:
    """List items for `documents`."""
    names = _uploader_names(db, documents)
    tags = tagging.tags_of(db, [d.id for d in documents])
    result = []
    for document in documents:
        out = DocumentOut.model_validate(document)
        out.unit_name, out.uploaded_by_name = unit_name(document.unit_id), names.get(document.uploaded_by_id, "")
        out.tags = tags.get(document.id, [])
        result.append(out)
    return result


def document_detail(db: Session, document: Document, viewer: User) -> DocumentDetail:
    """Full view of one document for `viewer`."""
    base = document_out(db, [document])[0]
    return DocumentDetail(**base.model_dump(), steps=document.steps or [], warnings=document.warnings or [],
                          secret_reasons=document.extra.get("placement_reasons", []),
                          can_manage=viewer.id == document.uploaded_by_id or viewer.role == "admin",
                          manual_tags=tagging.manual_of(db, document.id))
