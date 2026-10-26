"""Liveness and reference data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import config
from app.core.database import get_db
from app.models import User
from app.services import organization

from .deps import current_user

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness probe: the process is up and the database answers."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "name": config.APP_NAME, "version": config.APP_VERSION}


@router.get("/units")
def units(_: User = Depends(current_user)) -> list[dict]:
    """The organisation chart as a flat, ordered list (for filters and account forms)."""
    return organization.units_for_display()
