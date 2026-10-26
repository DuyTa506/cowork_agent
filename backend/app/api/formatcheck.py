"""Format and spelling check endpoints ("Kiểm tra thể thức"): temporary, private to the user, never indexed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CheckSession, User
from app.schemas.documents import DocumentOut
from app.schemas.formatcheck import CheckOptions, CheckOut, CheckRequest, FixOut, FixRequest, SaveRequest
from app.services import audit
from app.services.formatcheck import sessions

from .deps import attachment, client_ip, current_user
from .presenters import document_out

router = APIRouter(prefix="/api/format-check", tags=["format-check"])


def _out(row: CheckSession, payload: dict) -> CheckOut:
    """Response for a session and its payload."""
    return CheckOut(id=row.id, name=row.name, size=row.size, kind=row.kind, can_fix=row.kind == "word", profile=row.profile,
                    spell=row.spell, fixed=row.fixed, counts=row.counts, created_at=row.created_at, expires_at=row.expires_at,
                    result=payload)


@router.get("/options", response_model=CheckOptions)
def options(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Profiles, accepted file types, size limit and retention."""
    return sessions.options(db)


@router.post("", response_model=CheckOut, status_code=201)
def create(request: Request, file: UploadFile = File(...), profile: str | None = Form(None), spell: bool | None = Form(None),
           user: User = Depends(current_user), db: Session = Depends(get_db)) -> CheckOut:
    """Uploads a file privately and checks it."""
    row, payload = sessions.create(db, user, filename=file.filename or "", stream=file.file, profile=profile, spell=spell)
    audit.record(db, user, "format_check.run", entity_type="check", entity_id=row.id,
                 detail=f"{row.name}: {row.counts['format']} thể thức, {row.counts['spelling']} chính tả ({row.profile})", ip=client_ip(request))
    db.commit()
    return _out(row, payload)


@router.get("/{session_id}", response_model=CheckOut)
def read(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> CheckOut:
    """The last result of a session."""
    row = sessions.get(db, user, session_id)
    return _out(row, sessions.result(row))


@router.post("/{session_id}/recheck", response_model=CheckOut)
def recheck(session_id: str, body: CheckRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> CheckOut:
    """Checks the original again with other options."""
    row = sessions.get(db, user, session_id)
    payload = sessions.recheck(db, row, profile=body.profile, spell=body.spell)
    db.commit()
    return _out(row, payload)


@router.post("/{session_id}/fix", response_model=FixOut)
def fix(session_id: str, body: FixRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Applies the chosen edits and writes the corrected copy (download it from `/fixed`)."""
    row = sessions.get(db, user, session_id)
    outcome = sessions.fix(db, row, ids=body.ids, mode=body.mode)
    audit.record(db, user, "format_check.fix", entity_type="check", entity_id=row.id,
                 detail=f"{len(outcome['applied'])} mục đã sửa, {len(outcome['failed'])} không áp dụng được", ip=client_ip(request))
    db.commit()
    return outcome


@router.get("/{session_id}/file")
def original(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    """The file as uploaded (converted to .docx if it was .doc)."""
    row = sessions.get(db, user, session_id)
    return FileResponse(sessions.source_path(row), filename=row.name)


@router.get("/{session_id}/fixed")
def fixed(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    """The corrected copy."""
    row = sessions.get(db, user, session_id)
    return FileResponse(sessions.fixed_path(row), filename=f"{row.name.rsplit('.', 1)[0]}_da_sua.docx")


@router.get("/{session_id}/report")
def report(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Plain-text list of every finding."""
    data, filename = sessions.report(sessions.get(db, user, session_id))
    return Response(data, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": attachment(filename)})


@router.get("/{session_id}/annotated")
def annotated(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    """A copy of the document with the findings as Word comments."""
    row = sessions.get(db, user, session_id)
    return FileResponse(sessions.annotated(row), filename=f"{row.name.rsplit('.', 1)[0]}_ghi_chu.docx")


@router.post("/{session_id}/save", response_model=DocumentOut, status_code=201)
def save(session_id: str, body: SaveRequest, request: Request, user: User = Depends(current_user),
         db: Session = Depends(get_db)) -> DocumentOut:
    """Saves the original or corrected file into the document store (where it is indexed like any upload)."""
    row = sessions.get(db, user, session_id)
    document = sessions.save_to_store(db, user, row, which=body.which, declared_secret=body.declared_secret)
    audit.record(db, user, "document.upload", entity_type="document", entity_id=document.id,
                 detail=f"{document.original_name} (từ kiểm tra thể thức)", ip=client_ip(request))
    db.commit()
    return document_out(db, [document])[0]


@router.delete("/{session_id}", status_code=204)
def delete(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """Deletes the temporary file now."""
    sessions.delete(db, sessions.get(db, user, session_id))
    db.commit()
