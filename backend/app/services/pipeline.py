"""Turns an uploaded file into a searchable document. Runs in the worker, one document per call.

Steps (shown to the user as a progress list): read the file → extract metadata → decide unit and secrecy level → index.

Outcomes:

* ``ready``         indexed, with the key metadata extracted
* ``needs_review``  indexed, but something a person should check is missing (type, title, enough text)
* ``needs_ocr``     a PDF without a usable text layer; waits for the OCR service
* ``failed``        unreadable (password, corrupt, unsupported) or the embedding model is not configured

Infrastructure trouble (index unreachable) raises `IndexingUnavailable` so the worker retries instead of failing the document.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app import ocr, storage
from app.core import config
from app.models import Document, DocumentState
from app.models.base import now_utc
from app.org import Placement
from app.parsing import ParsedDocument, ParseError, parse_file
from app.search import EmbeddingNotConfigured

from . import indexing, organization, preview, tagging

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 200  # less than this is a title page or an empty shell, not a document worth answering from

STEPS = (("read", "Đọc nội dung"), ("metadata", "Trích xuất thông tin"), ("classify", "Xác định đơn vị và độ mật"),
         ("index", "Lập chỉ mục"))

# Document column -> attribute of the parser's Metadata; used to keep fields a person corrected by hand.
MANUAL_FIELDS = {"title": "title", "subject": "subject", "document_type": "doc_type", "document_number": "number", "symbol": "symbol",
                 "issuer": "issuing_agency", "issued_date": "date", "signer": "signer"}


class IndexingUnavailable(RuntimeError):
    """The search index or embedding server could not be reached; the job should be retried."""


class Progress:
    """Maintains `Document.steps` and commits after every change so the UI sees progress while the worker runs."""

    def __init__(self, db: Session, document: Document):
        self.db, self.document = db, document
        self.document.steps = [{"key": k, "label": label, "state": "pending", "detail": "", "at": None} for k, label in STEPS]
        self.db.commit()

    def _set(self, key: str, state: str, detail: str) -> None:
        steps = [dict(s) for s in self.document.steps]  # new list: SQLAlchemy does not see in-place JSON changes
        for step in steps:
            if step["key"] == key:
                step.update(state=state, detail=detail, at=now_utc().isoformat())
        self.document.steps = steps
        self.db.commit()

    def update(self, key: str, detail: str) -> None:
        """Shows what a running step is doing (for example the page OCR has reached)."""
        self._set(key, "running", detail)

    def running(self, key: str) -> None:
        """Marks the step as in progress."""
        self._set(key, "running", "")

    def done(self, key: str, detail: str = "") -> None:
        """Marks the step as finished."""
        self._set(key, "done", detail)

    def failed(self, key: str, detail: str) -> None:
        """Marks the step as failed, with the reason shown to the user."""
        self._set(key, "failed", detail)


def _finish(db: Session, document: Document, state: DocumentState, detail: str = "") -> None:
    """Stores the final state."""
    document.state, document.state_detail = state, detail
    db.commit()


def mark_failed(db: Session, document_id: int, detail: str) -> None:
    """Gives up on a document after the worker exhausted its retries."""
    document = db.get(Document, document_id)
    if document is not None:
        _finish(db, document, DocumentState.FAILED, detail)


def _apply_metadata(document: Document, parsed: ParsedDocument) -> None:
    """Copies extracted metadata onto the document, except fields a person corrected by hand (which then win in the index too)."""
    meta, manual = parsed.metadata, set(document.extra.get("manual", []))
    for column, attribute in MANUAL_FIELDS.items():
        if column in manual:
            setattr(meta, attribute, getattr(document, column))
        else:
            # Postgres enforces the column length (SQLite does not), and a stamp or a title run together can be longer than any field
            setattr(document, column, (getattr(meta, attribute) or "")[:getattr(Document, column).type.length])
    document.warnings = list(parsed.warnings)


def _review_reasons(parsed: ParsedDocument) -> list[str]:
    """What a person should look at; empty means the document is ready as is. A missing date alone is only a warning."""
    reasons = []
    if not parsed.metadata.doc_type:
        reasons.append("chưa nhận diện được loại văn bản")
    if not parsed.metadata.title.strip():
        reasons.append("chưa có trích yếu/tiêu đề")
    if len(parsed.text()) < MIN_TEXT_CHARS:
        reasons.append("nội dung quá ngắn")
    if parsed.metadata.stamped:  # a seal and a signature are on the page, so the number and the date must exist
        gaps = ocr.missing_stamp_fields(parsed)
        if gaps:
            reasons.append("đã có dấu/chữ ký nhưng chưa đọc được " + ", ".join(gaps))
    return reasons


def process(db: Session, document_id: int) -> None:
    """Runs the whole pipeline for one document and records the outcome on it.

    Raises:
        IndexingUnavailable: the index/embedding server failed; nothing is lost, the caller may retry.
    """
    document = db.get(Document, document_id)
    if document is None:
        log.warning("document %s vanished before processing", document_id)
        return
    document.state, document.state_detail = DocumentState.PROCESSING, ""
    progress = Progress(db, document)

    progress.running("read")
    key = storage.keys.document(document.stored_name)
    try:
        parsed = ocr.parse_with_ocr(key, lambda done, total: progress.update("read", f"OCR trang {done}/{total}"))
    except storage.BlobNotFound:
        progress.failed("read", "Tệp gốc không còn trong kho lưu trữ.")
        _finish(db, document, DocumentState.FAILED, "Tệp gốc không còn trong kho lưu trữ.")
        return
    except ocr.OcrError as exc:  # OCR is on but this file could not be read by it
        progress.failed("read", str(exc))
        _finish(db, document, DocumentState.NEEDS_OCR, f"{exc} Kiểm tra máy chủ OCR rồi chọn 'Xử lý lại'.")
        return
    except ParseError as exc:
        message = str(exc)
        progress.failed("read", message)
        if "lớp chữ" in message:  # PDF whose text cannot be extracted: a scan, or a font the extractor cannot decode
            _finish(db, document, DocumentState.NEEDS_OCR, message + " Bật OCR trong Quản trị → Hệ thống để đọc bản scan.")
        else:
            _finish(db, document, DocumentState.FAILED, message)
        return
    if not parsed.ocr:
        ocr.read_stamps(key, parsed)  # number/date/signer that were stamped on as pictures
    progress.done("read", f"{parsed.format.upper()}, {len(parsed.text()):,} ký tự".replace(",", ".") + (" (OCR)" if parsed.ocr else ""))

    if Path(document.original_name).suffix.lower() in preview.WORD_EXTENSIONS:
        preview.build(key)  # the page view of a Word file is drawn once here, not at every view (best effort: failures are logged)
    progress.running("metadata")
    _apply_metadata(document, parsed)
    reasons = _review_reasons(parsed)
    draft = not parsed.metadata.number and not parsed.metadata.date and not parsed.metadata.stamped
    if draft and parsed.metadata.date_text:  # say why the fields are empty, instead of leaving it to look like a parsing failure
        partial = parsed.metadata.date_partial
        known = (f" (chỉ có tháng {partial[5:]}/{partial[:4]})" if len(partial) == 7 else f" (chỉ có năm {partial})") if partial else ""
        document.warnings = [*document.warnings, f"Bản nháp: số và ngày ban hành còn để trống trên văn bản{known}."]
    tagging.replace_auto(db, document.id, tagging.auto_tags(title=document.title, issued_date=document.issued_date or parsed.metadata.date_partial,
                                                            head=parsed.text(), scanned=parsed.ocr, draft=draft))
    progress.done("metadata", document.document_type or "không rõ loại")

    progress.running("classify")
    declared = bool(document.extra.get("declared_secret"))
    stamp = parsed.metadata.classification
    secret_reasons = ([f"dấu độ mật trên văn bản ({stamp})"] if stamp else []) + (["người tải lên đánh dấu mật"] if declared else [])
    document.level = "mat" if secret_reasons else "thuong"
    document.extra = {**document.extra, "placement_reasons": secret_reasons}
    placement = Placement(document.unit_id, document.level, organization.tree().path_to(document.unit_id), tuple(secret_reasons))
    progress.done("classify", "Mật" if document.level == "mat" else "Thường")

    progress.running("index")
    try:
        index = indexing.current()
        document.chunk_count = index.index_document(str(document.id), parsed, placement)
        document.index_fingerprint = indexing.fingerprint()
    except EmbeddingNotConfigured as exc:
        progress.failed("index", str(exc))
        _finish(db, document, DocumentState.FAILED, f"{exc} Sau khi cấu hình, chọn 'Xử lý lại'.")
        return
    except Exception as exc:  # noqa: BLE001  (Qdrant/HTTP/timeouts: all mean "try again later")
        progress.failed("index", "Máy chủ chỉ mục hoặc embedding không phản hồi.")
        raise IndexingUnavailable(f"{type(exc).__name__}: {exc}") from exc
    progress.done("index", f"{document.chunk_count} đoạn")

    if reasons:
        _finish(db, document, DocumentState.NEEDS_REVIEW, "Cần bổ sung: " + "; ".join(reasons) + ".")
    else:
        _finish(db, document, DocumentState.READY)
    log.info("document %s -> %s (%s chunks)", document.id, document.state, document.chunk_count)

