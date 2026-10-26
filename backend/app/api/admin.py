"""Administration: accounts, system settings, audit trail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Document, User
from app.schemas.admin import AuditOut, SettingsSave, SettingsTest
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services import audit, documents, jobs, settings, users

from .deps import admin_user, client_ip
from .presenters import user_out

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


# ----- accounts -----
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    """All accounts."""
    return [user_out(u) for u in users.list_all(db)]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> UserOut:
    """Creates an account."""
    user = users.create(db, username=body.username, password=body.password, full_name=body.full_name, unit_id=body.unit_id, role=body.role)
    audit.record(db, admin, "user.create", entity_type="user", entity_id=user.id, detail=f"{user.username} / {user.role} / {user.unit_id}",
                 ip=client_ip(request))
    db.commit()
    return user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, admin: User = Depends(admin_user),
                db: Session = Depends(get_db)) -> UserOut:
    """Edits an account (role, unit, activation, password reset)."""
    user = users.get(db, user_id)
    changed = users.update(db, user, **body.model_dump(exclude_none=True))
    audit.record(db, admin, "user.update", entity_type="user", entity_id=user.id, detail=f"{user.username}: {', '.join(changed) or 'không đổi'}",
                 ip=client_ip(request))
    db.commit()
    return user_out(user)


# ----- system settings -----
@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    """All settings sections with field metadata and current values (secrets reported only as set / not set)."""
    return {**settings.public(db), "pending_jobs": jobs.pending(db)}


@router.put("/settings/{section}")
def save_settings(section: str, body: SettingsSave, request: Request, admin: User = Depends(admin_user),
                  db: Session = Depends(get_db)) -> dict:
    """Saves one section. Returns what changed and whether the documents must be indexed again."""
    before = settings.collection_name(settings.load(db, "embedding"))
    result = settings.save(db, section, body.values, actor=admin.username, confirm_hosts=body.confirm_hosts)
    detail = f"{section}: {', '.join(result['changed']) or 'không đổi'}"
    if result["new_hosts"]:
        detail += f"; xác nhận máy chủ ngoài mạng nội bộ: {', '.join(result['new_hosts'])}"
    audit.record(db, admin, "settings.save", entity_type="settings", entity_id=section, detail=detail, ip=client_ip(request))
    db.commit()
    reindex = section == "embedding" and settings.collection_name(settings.load(db, "embedding")) != before
    return {"changed": result["changed"], "reindex_required": reindex, "settings": {**settings.public(db), "pending_jobs": jobs.pending(db)}}


@router.post("/settings/{section}/test")
def test_settings(section: str, body: SettingsTest, db: Session = Depends(get_db)) -> dict:
    """Tries a connection with the given values (not saved)."""
    return settings.testing.run(section, settings.preview(db, section, body.values)).as_dict()


@router.post("/reindex")
def reindex(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    """Queues every document for indexing again (after changing the embedding model)."""
    count = documents.reindex_all(db)
    audit.record(db, admin, "index.rebuild", detail=f"{count} văn bản", ip=client_ip(request))
    db.commit()
    return {"queued": count}


# ----- audit trail -----
@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), action: str = "", username: str = "",
               db: Session = Depends(get_db)) -> list:
    """Newest-first audit rows."""
    return audit.recent(db, limit=limit, offset=offset, action=action, username=username)
