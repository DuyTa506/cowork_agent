"""Files attached to a chat: quick upload, parsing and indexing for that conversation only.

An attachment is parsed with the same engine as the document store (so an administrative document keeps its structure and
metadata; anything else is chunked as plain text) and indexed in a collection of its own. Search is confined to the conversation
by giving each chat a pseudo-unit, ``chat:<session id>``, in place of the organisation chart: the same permission filter that
protects the store then keeps one chat's files away from every other chat and from the store.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ocr, storage
from app.core import config
from app.core.errors import Conflict, NotFound
from app.models import AttachmentState, ChatAttachment, ChatSession, User
from app.org import Placement, Scope
from app.parsing import ParseError
from app.search import EmbeddingNotConfigured

from . import documents, indexing, jobs, settings
from .pipeline import IndexingUnavailable

log = logging.getLogger(__name__)

MAX_PER_SESSION = 10


def pseudo_unit(session_id: str) -> str:
    """The stand-in unit that owns a chat's attachments in the index."""
    return f"chat:{session_id}"


def scope_for(session_id: str) -> Scope:
    """Permission scope that reaches exactly the attachments of one chat."""
    unit = pseudo_unit(session_id)
    return Scope(unit, frozenset({unit}), frozenset({"thuong"}))


def doc_id(attachment_id: int) -> str:
    """Id of an attachment in the index (and in tool calls)."""
    return f"att{attachment_id}"


def blob_key(attachment: ChatAttachment) -> str:
    """Key of the attached file in the object store."""
    return storage.keys.attachment(attachment.session_id, attachment.stored_name)


def get(db: Session, user: User, attachment_id: int) -> ChatAttachment:
    """The user's own attachment, or `NotFound`."""
    row = db.scalar(select(ChatAttachment).where(ChatAttachment.id == attachment_id, ChatAttachment.user_id == user.id))
    if row is None:
        raise NotFound("Không tìm thấy tệp đính kèm.")
    return row


def list_for(db: Session, session_id: str) -> list[ChatAttachment]:
    """Attachments of a session, oldest first."""
    return list(db.scalars(select(ChatAttachment).where(ChatAttachment.session_id == session_id).order_by(ChatAttachment.id)))


def upload(db: Session, user: User, session: ChatSession, *, filename: str, stream: BinaryIO) -> ChatAttachment:
    """Stores a file for the conversation and queues it for indexing.

    Raises:
        Conflict: the conversation already has `MAX_PER_SESSION` files.
        ValidationFailed / PayloadTooLarge: as for `documents.save_upload`.
    """
    name = documents.safe_name(filename)
    extension = Path(name).suffix.lower()
    if extension not in documents.ALLOWED_EXTENSIONS:
        from app.core.errors import ValidationFailed
        raise ValidationFailed(f"Chỉ nhận tệp {', '.join(documents.ALLOWED_EXTENSIONS)}.")
    if len(list_for(db, session.id)) >= MAX_PER_SESSION:
        raise Conflict(f"Mỗi cuộc trò chuyện đính kèm tối đa {MAX_PER_SESSION} tệp.")
    limit = int(settings.load(db, "storage")["upload_max_mb"]) * 1024 * 1024
    stored = f"{uuid.uuid4().hex}{extension}"
    partial = config.TEMP_DIR / "upload" / f"{stored}.part"
    partial.parent.mkdir(parents=True, exist_ok=True)
    try:
        size, _ = documents.save_upload(stream, partial, limit)
        storage.get_store().put_file(storage.keys.attachment(session.id, stored), partial, storage.guess_content_type(stored))
    finally:
        partial.unlink(missing_ok=True)
    row = ChatAttachment(session_id=session.id, user_id=user.id, name=name, stored_name=stored, size=size, title=Path(name).stem)
    db.add(row)
    db.flush()
    jobs.enqueue(db, row.id, kind="attachment")
    return row


def process(db: Session, attachment_id: int) -> None:
    """Parses and indexes one attachment (runs in the worker).

    Raises:
        IndexingUnavailable: the index or embedding server failed; the job is retried.
    """
    row = db.get(ChatAttachment, attachment_id)
    if row is None:
        return
    row.state, row.detail = AttachmentState.PROCESSING, ""
    db.commit()
    try:
        parsed = ocr.parse_with_ocr(blob_key(row))
    except storage.BlobNotFound:
        mark_failed(db, attachment_id, "Tệp đính kèm không còn trong kho lưu trữ.")
        return
    except ocr.OcrError as exc:
        mark_failed(db, attachment_id, str(exc))
        return
    except ParseError as exc:
        message = str(exc)
        mark_failed(db, attachment_id, "PDF không có lớp chữ (bản scan) chưa đọc được trong cuộc trò chuyện." if "lớp chữ" in message else message)
        return
    parsed.metadata.title = parsed.metadata.title.strip() or Path(row.name).stem
    row.title, row.document_type = parsed.metadata.title[:500], parsed.metadata.doc_type
    unit = pseudo_unit(row.session_id)
    placement = Placement(unit, "thuong", (unit,), ())
    try:
        row.chunk_count = indexing.attachments().index_document(doc_id(row.id), parsed, placement)
    except EmbeddingNotConfigured as exc:
        mark_failed(db, attachment_id, str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        raise IndexingUnavailable(f"{type(exc).__name__}: {exc}") from exc
    row.state = AttachmentState.READY
    db.commit()


def mark_failed(db: Session, attachment_id: int, detail: str) -> None:
    """Records that an attachment cannot be used, with the reason shown to the user."""
    row = db.get(ChatAttachment, attachment_id)
    if row is not None:
        row.state, row.detail = AttachmentState.FAILED, detail
        db.commit()


def delete(db: Session, row: ChatAttachment) -> None:
    """Removes the file, its index entries and the record."""
    try:
        indexing.attachments_store_only().delete_document(doc_id(row.id))
    except Exception as exc:  # noqa: BLE001  (nothing is indexed yet, or the index is down; vectors of a deleted chat are unreachable anyway)
        log.warning("attachment %s: index cleanup failed: %s", row.id, exc)
    try:
        storage.get_store().delete(blob_key(row))
    except Exception as exc:  # noqa: BLE001
        log.warning("attachment %s: object delete failed: %s", row.id, exc)
    db.delete(row)


def delete_session_files(session_id: str) -> None:
    """Removes every file attached to a chat from the object store."""
    try:
        storage.get_store().delete_prefix(storage.keys.attachments_prefix(session_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("chat %s: removing attached files failed: %s", session_id, exc)
