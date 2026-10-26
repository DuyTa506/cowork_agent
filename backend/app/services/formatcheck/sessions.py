"""Format-check sessions: a user's temporary file, its results and its lifetime.

Layout on disk: ``TEMP_DIR/check/<id>/`` holds ``source.docx|pdf`` (what is checked), ``fixed.docx`` (after "Sửa"),
``result.json`` (the last payload) and ``original.name``. Nothing here is indexed or enters the document store unless the user
explicitly saves it (`save_to_store`).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config
from app.core.errors import NotFound, PayloadTooLarge, ValidationFailed
from app.models import CheckSession, Document, User
from app.models.base import now_utc

from .. import documents, settings
from . import engine

log = logging.getLogger(__name__)

ACCEPTED = (".docx", ".doc", ".pdf")
CHUNK = 1024 * 1024
ROOT = config.TEMP_DIR / "check"


def directory(session_id: str) -> Path:
    """Private directory of a session."""
    return ROOT / session_id


def options(db: Session) -> dict[str, Any]:
    """What the screen needs before a file is chosen: profiles, accepted types, size limit, retention."""
    values = settings.load(db, "doccheck")
    return {"profiles": engine.profiles(), "default_profile": values["profile"], "default_spell": values["spell"],
            "accept": list(ACCEPTED), "max_mb": int(settings.load(db, "storage")["upload_max_mb"]),
            "retention_hours": int(values["temp_retention_hours"])}


def get(db: Session, user: User, session_id: str, purpose: str = "format") -> CheckSession:
    """The user's own session of that screen, or `NotFound` (other users' sessions, other screens' sessions, expired ones and
    unknown ids look the same)."""
    row = db.scalar(select(CheckSession).where(CheckSession.id == session_id, CheckSession.user_id == user.id,
                                               CheckSession.purpose == purpose))
    if row is None or row.expires_at <= now_utc():
        raise NotFound("Không tìm thấy tệp kiểm tra (có thể đã hết hạn và bị xóa).")
    return row


def create(db: Session, user: User, *, filename: str, stream: BinaryIO, profile: str | None, spell: bool | None) -> tuple[CheckSession, dict]:
    """Stores the upload privately, checks it and returns the new session with its display payload.

    Raises:
        ValidationFailed: unsupported or unreadable file, scan without a text layer, unknown profile.
        PayloadTooLarge: larger than the configured limit.
    """
    purge_expired(db)
    name = documents.safe_name(filename)
    extension = Path(name).suffix.lower()
    if extension not in ACCEPTED:
        raise ValidationFailed(f"Chỉ nhận tệp {', '.join(ACCEPTED)}.")
    defaults = settings.load(db, "doccheck")
    profile = profile or defaults["profile"]
    spell = defaults["spell"] if spell is None else spell
    engine.rule_base(profile)  # unknown profile fails before anything is written
    limit = int(settings.load(db, "storage")["upload_max_mb"]) * 1024 * 1024

    session_id = secrets.token_hex(16)
    folder = directory(session_id)
    folder.mkdir(parents=True, mode=0o700)
    try:
        upload = folder / f"upload{extension}"
        size = _save(stream, upload, limit)
        source, kind = engine.prepare(upload, extension, folder)
        (folder / "original.name").write_text(name, encoding="utf-8")
        outcome = engine.analyze(source, kind, profile, spell, name, session_id)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    hours = int(defaults["temp_retention_hours"])
    row = CheckSession(id=session_id, user_id=user.id, name=name, kind=kind, size=size, profile=profile, spell=spell,
                       counts=outcome.counts, expires_at=now_utc() + timedelta(hours=hours))
    db.add(row)
    _write_result(session_id, outcome.payload)
    return row, outcome.payload


def _save(stream: BinaryIO, target: Path, limit: int) -> int:
    """Streams the upload to `target`, enforcing the size limit; returns the size."""
    size = 0
    with open(target, "wb") as out:
        while chunk := stream.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise PayloadTooLarge(f"Tệp vượt quá {limit // (1024 * 1024)} MB.")
            out.write(chunk)
    if size == 0:
        raise ValidationFailed("Tệp rỗng.")
    return size


def _write_result(session_id: str, payload: dict[str, Any]) -> None:
    """Keeps the last payload so reopening the screen does not recompute it."""
    (directory(session_id) / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def result(row: CheckSession) -> dict[str, Any]:
    """The last payload of the session."""
    return json.loads((directory(row.id) / "result.json").read_text(encoding="utf-8"))


def recheck(db: Session, row: CheckSession, *, profile: str | None, spell: bool | None) -> dict[str, Any]:
    """Checks the original file again, with other options; discards any corrected copy (it belonged to the old result)."""
    row.profile = profile or row.profile
    row.spell = row.spell if spell is None else spell
    source = source_path(row)
    outcome = engine.analyze(source, row.kind, row.profile, row.spell, row.name, row.id)
    (directory(row.id) / "fixed.docx").unlink(missing_ok=True)
    row.fixed, row.counts = False, outcome.counts
    _write_result(row.id, outcome.payload)
    return outcome.payload


def source_path(row: CheckSession) -> Path:
    """The file that is checked."""
    path = directory(row.id) / ("source.pdf" if row.kind == "pdf" else "source.docx")
    if not path.is_file():
        raise NotFound("Tệp đã bị xóa.")
    return path


def fixed_path(row: CheckSession) -> Path:
    """The corrected copy; `NotFound` before "Sửa" was used."""
    path = directory(row.id) / "fixed.docx"
    if not path.is_file():
        raise NotFound("Chưa có bản đã sửa.")
    return path


def fix(db: Session, row: CheckSession, *, ids: list[str], mode: str) -> dict[str, Any]:
    """Applies the chosen edits to the original (as Word tracked changes by default) and writes the corrected copy.

    Returns ``{"applied": [...], "failed": [{"id", "reason"}], "after": {"format", "spelling"}}`` where ``after`` is a fresh check
    of the corrected copy, so the screen can show how much is left.
    """
    if row.kind != "word":
        raise ValidationFailed("PDF không sửa trực tiếp được.")
    if not ids:
        raise ValidationFailed("Chưa chọn mục nào để sửa.")
    out = directory(row.id) / "fixed.docx"
    applied, failed = engine.apply(source_path(row), row.profile, row.spell, ids, mode, out)
    row.fixed = True
    after = engine.analyze(out, "word", row.profile, row.spell, row.name, row.id).counts
    return {"applied": applied, "failed": failed, "after": after}


def report(row: CheckSession) -> tuple[bytes, str]:
    """Plain-text report and its file name."""
    text = engine.report_text(source_path(row), row.profile, row.spell)
    lines = text.splitlines()
    if lines and lines[0].startswith("Tệp:"):  # doccheck prints the server-side path; show the name the user uploaded
        lines[0] = f"Tệp: {row.name}"
    return "\n".join(lines).encode("utf-8"), f"{Path(row.name).stem}_bao_cao.txt"


def annotated(row: CheckSession) -> Path:
    """Path of a copy of the document with findings as Word comments (made on demand)."""
    if row.kind != "word":
        raise ValidationFailed("Chỉ tệp Word mới có bản ghi chú.")
    out = directory(row.id) / "annotated.docx"
    engine.write_annotated(source_path(row), row.profile, row.spell, out)
    return out


def save_to_store(db: Session, user: User, row: CheckSession, *, which: str, declared_secret: bool) -> Document:
    """Promotes the original or corrected file to the document store (the only way a checked file gets indexed).

    Raises:
        ValidationFailed: `which` is not ``original`` or ``fixed``.
    """
    if which not in ("original", "fixed"):
        raise ValidationFailed("Chọn lưu bản gốc hoặc bản đã sửa.")
    path = fixed_path(row) if which == "fixed" else source_path(row)
    name = row.name if which == "original" or row.kind == "pdf" else f"{Path(row.name).stem}.docx"
    with open(path, "rb") as stream:
        return documents.upload(db, user, filename=name, stream=stream, declared_secret=declared_secret)


def delete(db: Session, row: CheckSession) -> None:
    """Removes the session and its files now."""
    shutil.rmtree(directory(row.id), ignore_errors=True)
    db.delete(row)


def purge_expired(db: Session) -> int:
    """Deletes expired sessions and any directory left without a row; returns how many sessions were removed. Called on every new
    check and periodically by the worker, so nothing outlives its retention period by long."""
    expired = db.scalars(select(CheckSession).where(CheckSession.expires_at <= now_utc())).all()
    for row in expired:
        delete(db, row)
    db.flush()
    if ROOT.is_dir():
        known = set(db.scalars(select(CheckSession.id)))
        for child in ROOT.iterdir():
            if child.is_dir() and child.name not in known and _age_seconds(child) > 3600:  # an upload may be in progress
                shutil.rmtree(child, ignore_errors=True)
    return len(expired)


def _age_seconds(path: Path) -> float:
    """Seconds since the directory was last modified."""
    return now_utc().timestamp() - os.stat(path).st_mtime
