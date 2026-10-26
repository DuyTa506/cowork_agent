"""Assistant endpoints: conversations, streaming answers, attached files and the draft (canvas)."""
from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app import moderation, storage
from app.agent.runtime import AgentPool
from app.core import config
from app.core.database import get_db
from app.core.errors import NotFound
from app.models import ChatAttachment, ChatSession, User
from app.schemas.chat import (AttachmentOut, DraftCheckOut, DraftCreate, DraftOut, DraftPatch, DraftSave, DraftSaved, MessageIn,
                              MessageOut, SessionCreate, SessionDetail, SessionOut, SessionRename)
from app.schemas.documents import Paragraph
from app.services import attachments, audit, chat, documents, drafts

from .blobs import blob_response
from .deps import agent_pool, client_ip, current_user, session_factory
from .presenters import document_out

router = APIRouter(prefix="/api/chat", tags=["chat"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ChatSession:
    """The signed-in user's conversation named in the path."""
    return chat.get(db, user, session_id)


def _attachment(attachment_id: int, session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> ChatAttachment:
    """An attachment of that conversation."""
    row = db.get(ChatAttachment, attachment_id)
    if row is None or row.session_id != session.id:
        raise NotFound("Không tìm thấy tệp đính kèm.")
    return row


# ----- conversations -----
@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ChatSession]:
    """The user's conversations, most recent first."""
    return chat.list_sessions(db, user)


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ChatSession:
    """Starts a conversation."""
    row = chat.create(db, user, body.title)
    db.commit()
    return row


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def read_session(session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> SessionDetail:
    """A conversation with its messages, attached files and draft."""
    draft = drafts.snapshot(db, session.id)
    return SessionDetail(session=session, messages=chat.messages(db, session.id), attachments=attachments.list_for(db, session.id),
                         draft=draft)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def rename_session(body: SessionRename, session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> ChatSession:
    """Renames a conversation."""
    chat.rename(db, session, body.title)
    db.commit()
    return session


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session: ChatSession = Depends(_session), db: Session = Depends(get_db), pool: AgentPool = Depends(agent_pool)) -> None:
    """Deletes a conversation with its messages, files and draft."""
    chat.delete_session(db, pool, session)
    db.commit()


@router.post("/sessions/{session_id}/warm", status_code=202)
def warm(session: ChatSession = Depends(_session), user: User = Depends(current_user), pool: AgentPool = Depends(agent_pool),
         factory=Depends(session_factory)) -> None:
    """Starts the assistant for this conversation in the background (call when the user focuses the message box)."""
    chat.warm_up(factory, pool, user.id, session.id)


# ----- answering -----
def _sse(turn: chat.Turn) -> Iterator[str]:
    """Server-sent events of a turn (comment lines keep proxies from closing a quiet connection)."""
    for item in turn.events():
        if item is None:
            yield ": keep-alive\n\n"
            continue
        name, data = item
        yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/sessions/{session_id}/messages")
def send_message(body: MessageIn, request: Request, session: ChatSession = Depends(_session), user: User = Depends(current_user),
                 db: Session = Depends(get_db), pool: AgentPool = Depends(agent_pool), factory=Depends(session_factory)) -> StreamingResponse:
    """Sends a message and streams what the assistant does and answers as server-sent events (see docs/CHAT_API.md)."""
    notice = moderation.screen(db, user, text=body.text, entity_id=session.id, ip=client_ip(request))
    turn = chat.prepare(db, user, session, text=body.text, attachment_ids=body.attachment_ids, canvas=body.canvas, context=body.context,
                        factory=factory, pool=pool)
    turn.notice = notice if notice and notice["action"] == "warn" else None
    turn.start()
    audit.record(db, user, "chat.ask", entity_type="chat", entity_id=session.id, detail=f"{len(body.text)} ký tự", ip=client_ip(request))
    db.commit()
    return StreamingResponse(_sse(turn), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@router.post("/sessions/{session_id}/stop", status_code=204)
def stop(session: ChatSession = Depends(_session)) -> None:
    """Stops the answer in progress."""
    turn = chat.active_turn(session.id)
    if turn is not None:
        turn.stop()


# ----- attached files -----
@router.post("/sessions/{session_id}/attachments", response_model=AttachmentOut, status_code=201)
def upload_attachment(request: Request, file: UploadFile = File(...), session: ChatSession = Depends(_session),
                      user: User = Depends(current_user), db: Session = Depends(get_db)) -> ChatAttachment:
    """Attaches a file to the conversation; it is indexed in the background (poll until `state` is `ready`)."""
    row = attachments.upload(db, user, session, filename=file.filename or "", stream=file.file)
    audit.record(db, user, "chat.attach", entity_type="chat", entity_id=session.id, detail=f"{row.name} ({row.size} bytes)",
                 ip=client_ip(request))
    db.commit()
    return row


@router.get("/sessions/{session_id}/attachments/{attachment_id}", response_model=AttachmentOut)
def read_attachment(row: ChatAttachment = Depends(_attachment)) -> ChatAttachment:
    """Processing state of an attached file."""
    return row


@router.delete("/sessions/{session_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(row: ChatAttachment = Depends(_attachment), db: Session = Depends(get_db)) -> None:
    """Removes an attached file."""
    attachments.delete(db, row)
    db.commit()


@router.get("/sessions/{session_id}/attachments/{attachment_id}/content", response_model=list[Paragraph])
def attachment_content(row: ChatAttachment = Depends(_attachment)) -> list[dict]:
    """Paragraphs of an attached file for the viewer."""
    try:
        with storage.get_store().local_copy(attachments.blob_key(row), config.TEMP_DIR) as path:
            return documents.paragraphs(path)
    except storage.BlobNotFound as exc:
        raise NotFound("Tệp đính kèm không còn trong kho lưu trữ.") from exc


@router.get("/sessions/{session_id}/attachments/{attachment_id}/file")
def attachment_file(request: Request, inline: bool = False, row: ChatAttachment = Depends(_attachment)) -> Response:
    """The attached file as uploaded (supports ``Range``)."""
    return blob_response(request, attachments.blob_key(row), row.name, inline=inline)


# ----- draft (canvas) -----
@router.get("/sessions/{session_id}/draft", response_model=DraftOut | None)
def read_draft(session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> dict | None:
    """The conversation's draft, or null."""
    return drafts.snapshot(db, session.id)


@router.post("/sessions/{session_id}/draft", response_model=DraftOut, status_code=201)
def create_draft(body: DraftCreate, session: ChatSession = Depends(_session), user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    """Opens an empty draft of a kind of document."""
    row = drafts.create(db, user, session, body.kind, replace=body.replace, by="user", unit=body.unit)
    db.commit()
    return drafts.view(row)


@router.patch("/sessions/{session_id}/draft", response_model=DraftOut)
def edit_draft(body: DraftPatch, session: ChatSession = Depends(_session), user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:
    """The user's edits to the draft."""
    row = drafts.get(db, session.id)
    if body.unit_id is not None:
        drafts.set_unit(db, row, user, body.unit_id)
    if body.style is not None:
        drafts.set_style(db, row, body.style.model_dump())
    drafts.user_edit(db, row, fields=body.fields, blocks=[b.model_dump() for b in body.blocks or []],
                     insert=body.insert.model_dump() if body.insert else None, delete_ids=body.delete, reviewed=body.reviewed)
    db.commit()
    return drafts.view(row)


@router.post("/sessions/{session_id}/draft/blocks/{block_id}/accept", response_model=DraftOut)
def accept_proposal(block_id: str, session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> dict:
    """Accepts the assistant's proposed change to a block."""
    row = drafts.get(db, session.id)
    drafts.decide(db, row, block_id, accept=True)
    db.commit()
    return drafts.view(row)


@router.post("/sessions/{session_id}/draft/blocks/{block_id}/reject", response_model=DraftOut)
def reject_proposal(block_id: str, session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> dict:
    """Rejects the assistant's proposed change to a block."""
    row = drafts.get(db, session.id)
    drafts.decide(db, row, block_id, accept=False)
    db.commit()
    return drafts.view(row)


@router.post("/sessions/{session_id}/draft/check", response_model=DraftCheckOut)
def check_draft(session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> dict:
    """Checks the draft against Thông tư 68 as the .docx would be written, its structure, and the wording against the style of
    the unit it is written for."""
    return drafts.check(db, drafts.get(db, session.id))


@router.get("/sessions/{session_id}/draft/export")
def export_draft(session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> Response:
    """The draft as a .docx."""
    row = drafts.get(db, session.id)
    with tempfile.TemporaryDirectory(prefix="draft-") as folder:
        path = drafts.export(db, row, Path(folder))
        data, name = path.read_bytes(), path.name
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_quote(name)}"})


@router.post("/sessions/{session_id}/draft/save", response_model=DraftSaved, status_code=201)
def save_draft(body: DraftSave, request: Request, session: ChatSession = Depends(_session), user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> DraftSaved:
    """Saves the draft into the document store."""
    document = drafts.save_to_store(db, user, drafts.get(db, session.id), declared_secret=body.declared_secret)
    audit.record(db, user, "document.upload", entity_type="document", entity_id=document.id,
                 detail=f"{document.original_name} (từ bản dự thảo)", ip=client_ip(request))
    db.commit()
    return DraftSaved(document=document_out(db, [document])[0])


@router.delete("/sessions/{session_id}/draft", status_code=204)
def delete_draft(session: ChatSession = Depends(_session), db: Session = Depends(get_db)) -> None:
    """Drops the draft."""
    drafts.delete(db, session.id)
    db.commit()


def _quote(name: str) -> str:
    from urllib.parse import quote
    return quote(name)
