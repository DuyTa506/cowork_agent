"""Document store endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError, DuplicateDocument, NotFound
from app.models import User
from app.ocr import render
from app.schemas.documents import (DocumentDetail, DocumentPage, Facets, MetadataUpdate, Paragraph, ScanOut, TagsUpdate, UploadItem,
                                   UploadResult)
from app.services import audit, documents, preview, scan, tagging

from .blobs import blob_response
from .deps import client_ip, current_user
from .presenters import document_detail, document_out

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentPage)
def list_documents(q: str = "", state: str = "", document_type: str = "", unit_id: str = "", level: str = "", date_from: str = "", date_to: str = "",
                   tag: list[str] = Query([]), sort: str = "uploaded_at", desc: bool = True, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> DocumentPage:
    """Documents the signed-in user may read, filtered and paged."""
    rows, total = documents.search(db, user, text=q, state=state, document_type=document_type, unit_id=unit_id, level=level,
                                   date_from=date_from, date_to=date_to, tags=tag, sort=sort, descending=desc, limit=limit, offset=offset)
    return DocumentPage(items=document_out(db, rows), total=total, states=documents.counts_by_state(db, user))


@router.get("/facets", response_model=Facets)
def facets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Facets:
    """Types, years and tags of the documents the user may read, with counts (for the filter panel)."""
    return Facets(**tagging.facets(db, user))


@router.post("", response_model=UploadResult, status_code=201)
def upload(request: Request, files: list[UploadFile] = File(...), declared_secret: bool = Form(False),
           user: User = Depends(current_user), db: Session = Depends(get_db)) -> UploadResult:
    """Uploads one or more files. Each file succeeds or fails on its own; the response says which."""
    items: list[UploadItem] = []
    for file in files:
        name = file.filename or ""
        try:
            document = documents.upload(db, user, filename=name, stream=file.file, declared_secret=declared_secret)
            audit.record(db, user, "document.upload", entity_type="document", entity_id=document.id,
                         detail=f"{document.original_name} ({document.file_size} bytes){' [đánh dấu mật]' if declared_secret else ''}",
                         ip=client_ip(request))
            db.commit()
            items.append(UploadItem(name=name, document=document_out(db, [document])[0]))
        except DuplicateDocument as exc:
            db.rollback()
            items.append(UploadItem(name=name, error=exc.message, code="duplicate", existing_id=exc.document_id or None))
        except AppError as exc:
            db.rollback()
            items.append(UploadItem(name=name, error=exc.message, code="error"))
    return UploadResult(items=items)


@router.get("/{document_id}", response_model=DocumentDetail)
def read_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> DocumentDetail:
    """One document with its processing steps."""
    return document_detail(db, documents.get(db, user, document_id), user)


@router.get("/{document_id}/content", response_model=list[Paragraph])
def read_content(document_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    """The document's text, paragraph by paragraph, for the viewer."""
    document = documents.get(db, user, document_id)
    audit.record(db, user, "document.view", entity_type="document", entity_id=document.id, ip=client_ip(request))
    db.commit()
    return documents.content(document)


@router.get("/{document_id}/scan", response_model=ScanOut)
def read_scan(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Page count and the positioned blocks of a scanned document (404 when it was not read with block positions)."""
    document = documents.get(db, user, document_id)
    return scan.blocks(documents.blob_key(document), documents.content(document))


@router.get("/{document_id}/pages/{number}")
def read_page(document_id: int, number: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Page `number` (from 1) of a scanned document as a PNG image."""
    document = documents.get(db, user, document_id)
    try:
        png = scan.page_png(documents.blob_key(document), number)
    except render.RenderError as exc:
        raise NotFound(str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{document_id}/preview")
def preview_file(document_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """The document as a PDF for the page viewer: the original PDF, or the one made from the Word file (built once, then kept).
    Streamed with ``Range`` support so the viewer fetches only the pages it shows."""
    document = documents.get(db, user, document_id)
    key = preview.key_for(documents.blob_key(document), document.original_name)
    if key is None:
        raise NotFound("Chưa dựng được bản xem trang của văn bản này.")
    return blob_response(request, key, Path(document.original_name).stem + ".pdf", inline=True, cacheable=True)


@router.get("/{document_id}/file")
def download(document_id: int, request: Request, inline: bool = False, user: User = Depends(current_user),
             db: Session = Depends(get_db)) -> Response:
    """The original file, streamed from the object store (supports ``Range``; `inline=true` lets a viewer show it in the page)."""
    document = documents.get(db, user, document_id)
    audit.record(db, user, "document.download", entity_type="document", entity_id=document.id, ip=client_ip(request))
    db.commit()
    return blob_response(request, documents.blob_key(document), document.original_name, inline=inline)


@router.put("/{document_id}/tags", response_model=DocumentDetail)
def set_tags(document_id: int, body: TagsUpdate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> DocumentDetail:
    """Replaces the hand-made tags (uploader or administrator); computed tags stay."""
    document = documents.get(db, user, document_id)
    documents.require_manage(user, document)
    tagging.set_manual(db, document.id, body.tags)
    audit.record(db, user, "document.tags", entity_type="document", entity_id=document.id, detail=", ".join(body.tags)[:200], ip=client_ip(request))
    db.commit()
    return document_detail(db, document, user)


@router.patch("/{document_id}", response_model=DocumentDetail)
def update_metadata(document_id: int, body: MetadataUpdate, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> DocumentDetail:
    """Corrects metadata by hand (uploader or administrator)."""
    document = documents.get(db, user, document_id)
    changed = documents.update_metadata(db, user, document, body.model_dump(exclude_none=True))
    if changed:
        audit.record(db, user, "document.update", entity_type="document", entity_id=document.id, detail=", ".join(changed),
                     ip=client_ip(request))
    db.commit()
    return document_detail(db, document, user)


@router.post("/{document_id}/reprocess", response_model=DocumentDetail)
def reprocess(document_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> DocumentDetail:
    """Queues the document for processing again."""
    document = documents.get(db, user, document_id)
    documents.reprocess(db, user, document)
    audit.record(db, user, "document.reprocess", entity_type="document", entity_id=document.id, ip=client_ip(request))
    db.commit()
    return document_detail(db, document, user)


@router.delete("/{document_id}", status_code=204)
def delete(document_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """Deletes the document, its file and its index entries (uploader or administrator)."""
    document = documents.get(db, user, document_id)
    label = f"{document.original_name} (#{document.id})"
    documents.delete(db, user, document)
    audit.record(db, user, "document.delete", entity_type="document", entity_id=document_id, detail=label, ip=client_ip(request))
    db.commit()
