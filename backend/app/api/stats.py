"""Dashboard figures (administrators and commanders)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.stats import Stats
from app.services import stats

from .deps import current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=Stats)
def read_stats(days: int = Query(30, description="Period of the usage figures: 7, 30 or 90 days."), user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:
    """Documents by state, type, unit and month, and what each unit did with the assistant in the period. An administrator sees
    the whole organisation, a commander their unit and the units under it; anyone else gets 403."""
    return stats.build(db, user, days)
