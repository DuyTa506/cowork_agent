"""Spelling check endpoints ("Kiểm tra chính tả"): temporary, private to the user, never indexed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CheckSession, User
from app.schemas.spellcheck import IgnoreRequest, SpellFixOut, SpellFixRequest, SpellOptions, SpellOut, TextRequest
from app.services import audit
from app.services.formatcheck import sessions as base
from app.services.spellcheck import sessions

from .deps import attachment, client_ip, current_user

router = APIRouter(prefix="/api/spellcheck", tags=["spellcheck"])


def _out(row: CheckSession) -> SpellOut:
    result = sessions.present(row)
    return SpellOut(id=row.id, name=row.name, size=row.size, kind=row.kind, can_fix=row.kind != "pdf", fixed=row.fixed,
                    counts={"spelling": result["counts"]["spelling"]}, ignore=sessions.ignored(row), created_at=row.created_at,
                    expires_at=row.expires_at, result=result)


@router.get("/options", response_model=SpellOptions)
def options(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Accepted file types, size and length limits, retention."""
    return sessions.options(db)


@router.post("", response_model=SpellOut, status_code=201)
def create(request: Request, file: UploadFile = File(...), markdown: bool | None = Form(None), user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> SpellOut:
    """Uploads a Word, PDF or text file privately and checks its spelling."""
    row = sessions.create_file(db, user, filename=file.filename or "", stream=file.file, markdown=markdown)
    audit.record(db, user, "spellcheck.run", entity_type="spellcheck", entity_id=row.id,
                 detail=f"{row.name}: {row.counts['spelling']} mục chính tả", ip=client_ip(request))
    db.commit()
    return _out(row)


@router.post("/text", response_model=SpellOut, status_code=201)
def create_text(body: TextRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SpellOut:
    """Checks the spelling of pasted text."""
    row = sessions.create_text(db, user, text=body.text, markdown=body.markdown)
    audit.record(db, user, "spellcheck.run", entity_type="spellcheck", entity_id=row.id,
                 detail=f"văn bản dán, {row.size} byte: {row.counts['spelling']} mục chính tả", ip=client_ip(request))
    db.commit()
    return _out(row)


@router.get("/{session_id}", response_model=SpellOut)
def read(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SpellOut:
    """The findings of a session."""
    return _out(sessions.get(db, user, session_id))


@router.put("/{session_id}/ignore", response_model=SpellOut)
def ignore(session_id: str, body: IgnoreRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SpellOut:
    """Sets the words this session must not report (the "bỏ qua tất cả" list)."""
    row = sessions.get(db, user, session_id)
    sessions.set_ignored(row, body.words)
    db.commit()
    return _out(row)


@router.post("/{session_id}/fix", response_model=SpellFixOut)
def fix(session_id: str, body: SpellFixRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Applies the chosen edits and writes the corrected copy (download it from `/fixed`)."""
    row = sessions.get(db, user, session_id)
    outcome = sessions.fix(row, ids=body.ids, mode=body.mode)
    if row.kind == "text":
        outcome["text"] = sessions.corrected_text(row)
    audit.record(db, user, "spellcheck.fix", entity_type="spellcheck", entity_id=row.id,
                 detail=f"{len(outcome['applied'])} chỗ đã sửa, {len(outcome['failed'])} không áp dụng được", ip=client_ip(request))
    db.commit()
    return outcome


@router.get("/{session_id}/file")
def original(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    """The file as uploaded (a .doc converted to .docx)."""
    row = sessions.get(db, user, session_id)
    return FileResponse(sessions.source_path(row), filename=row.name)


@router.get("/{session_id}/fixed")
def fixed(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    """The corrected copy."""
    row = sessions.get(db, user, session_id)
    return FileResponse(sessions.fixed_path(row), filename=sessions.download_name(row))


@router.get("/{session_id}/report")
def report(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Plain-text list of the findings."""
    data, filename = sessions.report(sessions.get(db, user, session_id))
    return Response(data, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": attachment(filename)})


@router.delete("/{session_id}", status_code=204)
def delete(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """Deletes the temporary file now."""
    base.delete(db, sessions.get(db, user, session_id))
    db.commit()
