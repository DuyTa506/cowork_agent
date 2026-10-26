"""Spelling-check sessions: the user's temporary file or pasted text, its findings and its lifetime.

Same machinery as "Kiểm tra thể thức" (`CheckSession` rows with ``purpose="spell"``, a private directory under ``TEMP_DIR/check/<id>/``,
expiry by `doccheck.temp_retention_hours`). The directory holds ``source.docx|pdf|txt`` (what is checked), ``result.json`` (the findings
before the ignore list), ``ignore.json`` (the words the user told the screen to skip), ``meta.json`` (text files: encoding, line ends,
Markdown) and ``fixed.docx|txt`` after "Sửa". Nothing here is indexed or enters the document store.
"""
from __future__ import annotations

import json
import secrets
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.models import CheckSession, User
from app.models.base import now_utc

from .. import documents, settings
from ..formatcheck import engine as format_engine
from ..formatcheck import sessions as base
from . import engine

PURPOSE = "spell"
ACCEPTED = (".docx", ".doc", ".pdf", *engine.TEXT_EXTENSIONS)
MAX_IGNORED = 500


def options(db: Session) -> dict[str, Any]:
    """What the screen needs before anything is checked."""
    values = settings.load(db, "doccheck")
    return {"accept": list(ACCEPTED), "max_mb": int(settings.load(db, "storage")["upload_max_mb"]), "max_chars": engine.MAX_CHARS,
            "retention_hours": int(values["temp_retention_hours"])}


def get(db: Session, user: User, session_id: str) -> CheckSession:
    """The user's own spelling session, or `NotFound`."""
    return base.get(db, user, session_id, PURPOSE)


# ----- files in the session directory -----
def _read_json(session_id: str, name: str, default: Any) -> Any:
    path = base.directory(session_id) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write_json(session_id: str, name: str, value: Any) -> None:
    (base.directory(session_id) / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _new_folder() -> tuple[str, Path]:
    session_id = secrets.token_hex(16)
    folder = base.directory(session_id)
    folder.mkdir(parents=True, mode=0o700)
    return session_id, folder


def _register(db: Session, user: User, session_id: str, *, name: str, kind: str, size: int, payload: dict[str, Any]) -> CheckSession:
    hours = int(settings.load(db, "doccheck")["temp_retention_hours"])
    row = CheckSession(id=session_id, user_id=user.id, name=name, kind=kind, purpose=PURPOSE, size=size,
                       profile=settings.load(db, "doccheck")["profile"], spell=True, counts={"format": 0, "spelling": payload["counts"]["spelling"]},
                       expires_at=now_utc() + timedelta(hours=hours))
    db.add(row)
    _write_json(session_id, "result.json", payload)
    return row


# ----- creating -----
def create_file(db: Session, user: User, *, filename: str, stream: BinaryIO, markdown: bool | None) -> CheckSession:
    """Stores the upload privately and checks its spelling.

    Raises:
        ValidationFailed: unsupported or unreadable file, scan without a text layer.
        PayloadTooLarge: larger than the configured limit.
    """
    base.purge_expired(db)
    name = documents.safe_name(filename)
    extension = Path(name).suffix.lower()
    if extension not in ACCEPTED:
        raise ValidationFailed(f"Chỉ nhận tệp {', '.join(ACCEPTED)}.")
    limit = int(settings.load(db, "storage")["upload_max_mb"]) * 1024 * 1024
    session_id, folder = _new_folder()
    try:
        upload = folder / f"upload{extension}"
        size = base._save(stream, upload, limit)
        if extension in engine.TEXT_EXTENSIONS:
            payload, meta = _analyze_text_file(upload, name, extension, markdown, folder)
            row = _register(db, user, session_id, name=name, kind="text", size=size, payload=payload)
            _write_json(session_id, "meta.json", meta)
        else:
            source, kind = format_engine.prepare(upload, extension, folder)
            profile = settings.load(db, "doccheck")["profile"]
            payload = engine.analyze_file(source, kind, profile, name, session_id)
            row = _register(db, user, session_id, name=name, kind=kind, size=size, payload=payload)
        (folder / "original.name").write_text(name, encoding="utf-8")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return row


def _analyze_text_file(upload: Path, name: str, extension: str, markdown: bool | None, folder: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = upload.read_bytes()
    text, encoding, note = engine.decode_text(raw)
    text, eol = _lines(text)
    markdown = extension in engine.MARKDOWN_EXTENSIONS if markdown is None else markdown
    payload = engine.analyze_text(text, name, markdown, encoding, eol, note)
    upload.rename(folder / "source.txt")
    (folder / "text.txt").write_text(text, encoding="utf-8")  # normalised lines: what the offsets of the findings refer to
    return payload, {"enc": encoding, "eol": eol, "ext": extension, "markdown": markdown}


def _lines(text: str) -> tuple[str, str]:
    """``(text with "\\n" line ends, the line end the input used)``."""
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), eol


def create_text(db: Session, user: User, *, text: str, markdown: bool) -> CheckSession:
    """Checks pasted text (kept privately like a file, so it can be corrected and downloaded).

    Raises:
        ValidationFailed: empty or too long.
    """
    base.purge_expired(db)
    text, eol = _lines(text)
    payload = engine.analyze_text(text, "", markdown, "utf-8", eol)
    session_id, folder = _new_folder()
    try:
        (folder / "text.txt").write_text(text, encoding="utf-8")
        name = "van_ban.txt"
        (folder / "original.name").write_text(name, encoding="utf-8")
        row = _register(db, user, session_id, name=name, kind="text", size=len(text.encode("utf-8")), payload=payload)
        _write_json(session_id, "meta.json", {"enc": "utf-8", "eol": eol, "ext": ".txt", "markdown": markdown, "pasted": True})
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return row


# ----- reading -----
def ignored(row: CheckSession) -> list[str]:
    """The words the user asked the screen to skip in this session."""
    return _read_json(row.id, "ignore.json", [])


def present(row: CheckSession) -> dict[str, Any]:
    """The findings as the screen shows them: the stored payload without the ignored words."""
    return engine.apply_ignore(_read_json(row.id, "result.json", {}), ignored(row))


def set_ignored(row: CheckSession, words: list[str]) -> dict[str, Any]:
    """Replaces the ignore list; returns the findings without those words (the corrected copy, if any, is left alone)."""
    clean: list[str] = []
    for word in words:
        word = " ".join(word.split())
        if word and len(word) <= 80 and engine.normalize_word(word) not in {engine.normalize_word(w) for w in clean}:
            clean.append(word)
    if len(clean) > MAX_IGNORED:
        raise ValidationFailed(f"Danh sách bỏ qua tối đa {MAX_IGNORED} từ.")
    _write_json(row.id, "ignore.json", clean)
    payload = present(row)
    row.counts = {"format": 0, "spelling": payload["counts"]["spelling"]}
    return payload


def source_path(row: CheckSession) -> Path:
    """The file that was checked (text sessions: the original file or the pasted text)."""
    if row.kind == "text":
        for candidate in ("source.txt", "text.txt"):
            if (base.directory(row.id) / candidate).is_file():
                return base.directory(row.id) / candidate
        raise NotFound("Tệp đã bị xóa.")
    return base.source_path(row)


def fixed_path(row: CheckSession) -> Path:
    """The corrected copy; `NotFound` before "Sửa" was used."""
    path = base.directory(row.id) / ("fixed.txt" if row.kind == "text" else "fixed.docx")
    if not path.is_file():
        raise NotFound("Chưa có bản đã sửa.")
    return path


def download_name(row: CheckSession) -> str:
    """File name of the corrected copy: ``<name>_sua.docx`` or ``<name>_sua<.txt|.md>``."""
    stem = Path(row.name).stem
    if row.kind == "text":
        return f"{stem}_sua{_read_json(row.id, 'meta.json', {}).get('ext', '.txt')}"
    return f"{stem}_sua.docx"


# ----- correcting -----
def fix(row: CheckSession, *, ids: list[str], mode: str) -> dict[str, Any]:
    """Writes the corrected copy with the chosen edits.

    Returns ``{"applied": [...], "failed": [{"id", "reason"}], "after": {"spelling": n}}``; ``after`` counts what a new check of the
    corrected copy still finds (without the ignored words).
    """
    if row.kind == "pdf":
        raise ValidationFailed("PDF không sửa trực tiếp được.")
    if not ids:
        raise ValidationFailed("Chưa chọn mục nào để sửa.")
    folder = base.directory(row.id)
    payload = present(row)
    if row.kind == "text":
        meta = _read_json(row.id, "meta.json", {})
        text = (folder / "text.txt").read_text(encoding="utf-8")
        corrected, applied, failed = engine.correct_text(text, payload["items"], ids)
        out = corrected.replace("\n", meta.get("eol", "\n"))
        (folder / "fixed.txt").write_bytes(out.encode(meta.get("enc", "utf-8") if meta.get("enc") != "utf-8-sig" else "utf-8-sig"))
        after = engine.analyze_text(corrected, row.name, bool(meta.get("markdown"))) if corrected.strip() else {"counts": {"spelling": 0}}
        remaining = engine.apply_ignore(after, ignored(row))["counts"]["spelling"] if "items" in after else 0
    else:
        if mode not in ("track", "apply"):
            raise ValidationFailed("Chế độ sửa phải là 'track' hoặc 'apply'.")
        applied, failed = engine.apply_word(base.source_path(row), row.profile, ids, mode, folder / "fixed.docx")
        again = engine.analyze_file(folder / "fixed.docx", "word", row.profile, row.name, row.id)
        remaining = engine.apply_ignore(again, ignored(row))["counts"]["spelling"]
    row.fixed = True
    return {"applied": applied, "failed": failed, "after": {"spelling": remaining}}


def report(row: CheckSession) -> tuple[bytes, str]:
    """Plain-text report of the findings still shown, and its file name."""
    return engine.report_text(row.name, present(row)).encode("utf-8"), f"{Path(row.name).stem}_chinh_ta.txt"


def corrected_text(row: CheckSession) -> str:
    """The corrected text of a text session (for the "Chép" button)."""
    return fixed_path(row).read_bytes().decode(_read_json(row.id, "meta.json", {}).get("enc", "utf-8"), errors="replace")
