"""Audit trail: who did what, to what, from where. Append-only."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User

MAX_DETAIL = 4000


def record(db: Session, actor: User | None, action: str, *, entity_type: str = "", entity_id: str | int = "",
           detail: str = "", ip: str = "") -> None:
    """Adds an audit row to the session; it is committed together with the change it describes.

    Args:
        actor: The signed-in user, or None for actions by the system itself (worker, start-up).
        action: Stable dotted identifier such as ``document.upload`` or ``settings.save``.
        detail: Free text for a human reader. Never put document content, passwords or API keys here.
    """
    db.add(AuditLog(user_id=actor.id if actor else None, username=actor.username if actor else "system", action=action,
                    entity_type=entity_type, entity_id=str(entity_id), detail=detail[:MAX_DETAIL], ip_address=ip))


def recent(db: Session, *, limit: int = 100, offset: int = 0, action: str = "", username: str = "") -> list[AuditLog]:
    """Newest-first slice of the trail, optionally narrowed to an action prefix or one user."""
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)).offset(max(offset, 0))
    if action:
        query = query.where(AuditLog.action.like(action.replace("%", "") + "%"))
    if username:
        query = query.where(AuditLog.username == username)
    return list(db.scalars(query))
