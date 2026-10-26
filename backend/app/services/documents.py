"""The document store: upload, listing with permissions, metadata edits, deletion, content view.

Who may read a document is decided in one place, `readable_clause`, and applied inside the SQL query so a document the user
may not see never leaves the database (and cannot be revealed by paging or counting).
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import date
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import and_, func, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core import config
from app.core.errors import DuplicateDocument, Forbidden, NotFound, PayloadTooLarge, ServiceUnavailable, ValidationFailed
from app.models import Document, DocumentState, DocumentTag, User
from app.parsing.reader import ReadError, load_model, to_lines

from app import ocr, storage

from . import indexing, jobs, organization, preview, settings

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = (".doc", ".docx", ".pdf")
_MAGIC = (b"\xd0\xcf\x11\xe0", b"PK\x03\x04", b"%PDF")  # OLE (.doc), ZIP (.docx), PDF
CHUNK = 1024 * 1024
# States in which the secrecy level is not yet known (it comes from the stamp inside the file), so only the uploader sees them.
UNCLASSIFIED = (DocumentState.UPLOADED, DocumentState.PROCESSING, DocumentState.NEEDS_OCR, DocumentState.FAILED)
EDITABLE_FIELDS = ("title", "subject", "document_type", "document_number", "symbol", "issuer", "issued_date", "signer")
SORTS = {"uploaded_at": Document.uploaded_at, "issued_date": Document.issued_date, "title": Document.title}


# --------------------------------------------------------------------------------------------------------------------------
# permissions
# --------------------------------------------------------------------------------------------------------------------------
def readable_clause(user: User) -> ColumnElement[bool]:
    """SQL condition for the documents `user` may read.

    A classified document is readable when its unit is in the user's subtree and its level is one the role may read. A document
    whose level is not known yet is readable by its uploader only.
    """
    scope = organization.scope_of(user)
    own_unclassified = and_(Document.uploaded_by_id == user.id, Document.state.in_(UNCLASSIFIED))
    if not scope.unit_ids or not scope.levels:
        return own_unclassified
    classified = and_(Document.unit_id.in_(scope.unit_ids), Document.level.in_(scope.levels), Document.state.notin_(UNCLASSIFIED))
    return or_(classified, own_unclassified)


def get(db: Session, user: User, document_id: int) -> Document:
    """The document, if `user` may read it. Not found and not allowed are indistinguishable on purpose."""
    document = db.scalar(select(Document).where(Document.id == document_id, readable_clause(user)))
    if document is None:
        raise NotFound("Không tìm thấy văn bản.")
    return document


def require_manage(user: User, document: Document) -> None:
    """Editing and deleting are for the uploader and administrators."""
    if user.id != document.uploaded_by_id and user.role != "admin":
        raise Forbidden("Chỉ người tải lên hoặc quản trị viên được thay đổi văn bản này.")


# --------------------------------------------------------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------------------------------------------------------
def search(db: Session, user: User, *, text: str = "", state: str = "", document_type: str = "", unit_id: str = "",
           level: str = "", date_from: str = "", date_to: str = "", tags: list[str] | None = None, sort: str = "uploaded_at",
           descending: bool = True, limit: int = 50, offset: int = 0) -> tuple[list[Document], int]:
    """A page of readable documents and the total that match.

    `text` matches title, number, symbol, the combined "number/symbol" (``16/QĐ-QK3``), issuer and file name. `state` may list
    several states separated by commas, and so may `document_type`. `unit_id` selects that unit and everything below it.
    """
    clauses = [readable_clause(user)]
    if text.strip():
        like = f"%{text.strip().lower()}%"
        combined = func.lower(func.coalesce(Document.document_number, "") + "/" + func.coalesce(Document.symbol, ""))
        clauses.append(or_(combined.like(like), *(func.lower(c).like(like) for c in (Document.title, Document.subject, Document.document_number, Document.symbol,
                                                                                     Document.original_name, Document.issuer))))
    states = [v for v in state.split(",") if v]
    if states:
        clauses.append(Document.state.in_(states))
    types = [v for v in document_type.split(",") if v]
    if types:
        clauses.append(Document.document_type.in_(types))
    if level:
        clauses.append(Document.level == level)
    for tag in tags or []:  # every chosen tag must be on the document
        clauses.append(Document.id.in_(select(DocumentTag.document_id).where(DocumentTag.tag == tag)))
    if unit_id:
        tree = organization.tree()
        clauses.append(Document.unit_id.in_(tree.subtree(unit_id) if unit_id in tree.units else [unit_id]))
    if date_from:
        clauses.append(Document.issued_date >= date_from)
    if date_to:
        clauses.append(and_(Document.issued_date != "", Document.issued_date <= date_to))
    total = db.scalar(select(func.count()).select_from(Document).where(*clauses)) or 0
    order = SORTS.get(sort, Document.uploaded_at)
    rows = db.scalars(select(Document).where(*clauses).order_by(order.desc() if descending else order.asc(), Document.id.desc())
                      .limit(min(max(limit, 1), 200)).offset(max(offset, 0))).all()
    return list(rows), total


def counts_by_state(db: Session, user: User) -> dict[str, int]:
    """Readable documents per state, for the filter chips on the list screen."""
    rows = db.execute(select(Document.state, func.count()).where(readable_clause(user)).group_by(Document.state)).all()
    return {state: count for state, count in rows}


# --------------------------------------------------------------------------------------------------------------------------
# upload
# --------------------------------------------------------------------------------------------------------------------------
def safe_name(filename: str) -> str:
    """Display name: the last path component only, bounded in length."""
    return os.path.basename(filename.replace("\\", "/")).strip()[:255] or "tai-lieu"


def upload(db: Session, user: User, *, filename: str, stream: BinaryIO, declared_secret: bool = False) -> Document:
    """Stores an uploaded file and queues it for processing.

    The file is streamed to a temporary file (never held whole in memory) while its size and hash are computed, then put in the
    object store. The document belongs to the
    uploader's unit; it becomes secret when the uploader says so or the worker finds a secrecy stamp in it.

    Raises:
        ValidationFailed: unsupported extension, empty file, or content that is not a Word/PDF file.
        PayloadTooLarge: larger than the administrator's limit.
        DuplicateDocument: the same file is already in the user's unit.
    """
    name = safe_name(filename)
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationFailed(f"Chỉ nhận tệp {', '.join(ALLOWED_EXTENSIONS)}.")
    if user.unit_id not in organization.tree().units:
        raise Forbidden("Tài khoản chưa được gán đơn vị hợp lệ nên chưa thể tải văn bản lên.")
    limit = int(settings.load(db, "storage")["upload_max_mb"]) * 1024 * 1024

    stored = f"{uuid.uuid4().hex}{extension}"
    partial = config.TEMP_DIR / "upload" / f"{stored}.part"
    partial.parent.mkdir(parents=True, exist_ok=True)
    try:
        size, digest = save_upload(stream, partial, limit)
        _reject_duplicate(db, user, digest)
        storage.get_store().put_file(storage.keys.document(stored), partial, storage.guess_content_type(stored))
    finally:
        partial.unlink(missing_ok=True)

    document = Document(original_name=name, stored_name=stored, file_size=size, sha256=digest, unit_id=user.unit_id,
                        level="mat" if declared_secret else "thuong", state=DocumentState.UPLOADED, uploaded_by_id=user.id,
                        extra={"declared_secret": declared_secret}, title=Path(name).stem)
    db.add(document)
    db.flush()
    jobs.enqueue(db, document.id)
    return document


def save_upload(stream: BinaryIO, target: Path, limit: int) -> tuple[int, str]:
    """Streams an upload to `target` (never holding it whole in memory) and returns ``(size, sha256 hex)``.

    Raises:
        ValidationFailed: empty, or the content is not a Word/PDF file (the first bytes decide, not the extension).
        PayloadTooLarge: more than `limit` bytes.
    """
    digest, size = hashlib.sha256(), 0
    with open(target, "wb") as out:
        while chunk := stream.read(CHUNK):
            if size == 0 and not chunk.startswith(_MAGIC):
                raise ValidationFailed("Nội dung tệp không phải Word hoặc PDF.")
            size += len(chunk)
            if size > limit:
                raise PayloadTooLarge(f"Tệp vượt quá {limit // (1024 * 1024)} MB.")
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        raise ValidationFailed("Tệp rỗng.")
    return size, digest.hexdigest()


def _reject_duplicate(db: Session, user: User, sha256: str) -> None:
    """Raises `DuplicateDocument` when the user's unit already holds this exact file. The id of the existing document is revealed
    only if the user may read it."""
    existing = db.scalar(select(Document).where(Document.sha256 == sha256, Document.unit_id == user.unit_id).order_by(Document.id))
    if existing is None:
        return
    if db.scalar(select(Document.id).where(Document.id == existing.id, readable_clause(user))):
        raise DuplicateDocument(f"Tệp này đã có trong kho (văn bản #{existing.id}).", existing.id)
    raise DuplicateDocument("Tệp này đã có trong kho của đơn vị.", 0)


# --------------------------------------------------------------------------------------------------------------------------
# changes
# --------------------------------------------------------------------------------------------------------------------------
def update_metadata(db: Session, user: User, document: Document, fields: dict[str, str]) -> list[str]:
    """Corrects extracted metadata by hand and queues re-indexing so search sees the change.

    Corrected fields are remembered (`extra["manual"]`) and survive re-processing. Returns the fields that changed.
    """
    require_manage(user, document)
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        raise ValidationFailed(f"Không được sửa trường: {', '.join(unknown)}.")
    if "issued_date" in fields and fields["issued_date"] and not _is_iso_date(fields["issued_date"]):
        raise ValidationFailed("Ngày ban hành phải có dạng năm-tháng-ngày, ví dụ 2026-05-04.")
    changed = []
    for name, value in fields.items():
        value = value.strip()
        if getattr(document, name) != value:
            setattr(document, name, value)
            changed.append(name)
    if changed:
        document.extra = {**document.extra, "manual": sorted(set(document.extra.get("manual", [])) | set(changed))}
        if document.state in (DocumentState.READY, DocumentState.NEEDS_REVIEW):
            jobs.enqueue(db, document.id)
    return changed


def _is_iso_date(value: str) -> bool:
    """True for a real calendar date written yyyy-mm-dd."""
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def reprocess(db: Session, user: User, document: Document) -> None:
    """Queues the document for processing again (after fixing the configuration, or when the parser has improved)."""
    require_manage(user, document)
    document.state, document.state_detail = DocumentState.UPLOADED, ""
    jobs.enqueue(db, document.id)


def reindex_all(db: Session) -> int:
    """Queues every document that was indexed (or should have been) for processing; returns how many. Used after the embedding
    model changed. Administrators only (checked by the caller)."""
    ids = db.scalars(select(Document.id).where(Document.state.in_([DocumentState.READY, DocumentState.NEEDS_REVIEW,
                                                                     DocumentState.FAILED, DocumentState.UPLOADED]))).all()
    for document_id in ids:
        jobs.enqueue(db, document_id)
    return len(ids)


def delete(db: Session, user: User, document: Document) -> None:
    """Removes the file, its chunks in the index and the record.

    The index goes first and a failure there aborts the deletion: a record removed while its chunks remained would leave text
    that search can still return.
    """
    require_manage(user, document)
    try:
        indexing.store_only().delete_document(str(document.id))
    except Exception as exc:  # noqa: BLE001
        log.error("index delete failed for document %s: %s", document.id, exc)
        raise ServiceUnavailable("Không xóa được dữ liệu trong chỉ mục; chưa xóa văn bản. Thử lại sau.") from exc
    try:
        storage.get_store().delete(blob_key(document))
        storage.get_store().delete(ocr.companion_key(blob_key(document)))
        storage.get_store().delete(ocr.grounding_key(blob_key(document)))
        storage.get_store().delete(preview.view_key(blob_key(document)))
    except Exception as exc:  # noqa: BLE001  (the object is unreachable once the record is gone; do not keep the record for it)
        log.warning("object delete failed for document %s: %s", document.id, exc)
    db.execute(sql_delete(DocumentTag).where(DocumentTag.document_id == document.id))
    db.delete(document)


# --------------------------------------------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------------------------------------------
def blob_key(document: Document) -> str:
    """Key of the document's original file in the object store."""
    return storage.keys.document(document.stored_name)


def content(document: Document) -> list[dict]:
    """The document's paragraphs for the viewer (see `paragraphs`); `NotFound` when the original is gone from storage."""
    store = storage.get_store()
    text_key = ocr.companion_key(blob_key(document))  # a scan is shown through the text OCR read from it
    try:
        with store.local_copy(text_key if store.exists(text_key) else blob_key(document), config.TEMP_DIR) as path:
            return paragraphs(path)
    except storage.BlobNotFound as exc:
        raise NotFound("Tệp gốc không còn trong kho lưu trữ.") from exc


def paragraphs(path: Path) -> list[dict]:
    """Paragraphs of the file at `path` for the viewer, each with its source index ``pi`` (the same index search results cite, so the
    viewer can highlight a cited passage). Page headers and footers are excluded."""
    try:
        model, _, _ = load_model(path)
    except ReadError as exc:
        raise ValidationFailed(str(exc)) from exc
    return [{"pi": line.pi, "text": line.text, "align": line.align, "bold": line.bold, "italic": line.italic,
             "table": line.table, "row": line.row, "col": line.col}
            for line in to_lines(model) if not line.empty]
