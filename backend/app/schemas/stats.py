"""Dashboard payloads."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CountItem(BaseModel):
    """One bar of a chart: a stable key, the text shown and how many."""

    key: str
    label: str
    count: int


class UnitCount(BaseModel):
    """Documents directly in one unit, with the top-level branch (Bộ Tham mưu, Cục Chính trị...) it belongs to."""

    unit_id: str
    name: str
    branch_id: str
    branch: str
    count: int


class DayCount(BaseModel):
    day: str  # yyyy-mm-dd, Vietnam time
    count: int


class UnitUsage(BaseModel):
    """What the people of one unit did in the chosen period."""

    unit_id: str
    name: str
    branch_id: str
    branch: str
    users: int  # accounts of the unit
    active_users: int  # of them, how many did anything in the period
    questions: int  # messages sent to the assistant
    uploads: int  # documents uploaded
    moderation: int  # messages the input screening objected to
    series: list[int]  # questions per day over the period (for the sparkline)


class ModerationEvent(BaseModel):
    at: datetime
    username: str
    unit_name: str
    action: str  # block | warn | log


class Totals(BaseModel):
    documents: int
    ready: int
    needs_review: int
    needs_ocr: int
    failed: int
    processing: int  # waiting or being read
    secret: int
    scanned: int  # read with OCR
    chunks: int
    users: int
    active_users: int
    questions_period: int
    questions_month: int
    uploads_period: int
    moderation_period: int


class StatsScope(BaseModel):
    unit_id: str
    unit_name: str
    everything: bool  # the whole organisation (administrators)


class CanvasUsage(BaseModel):
    """Decisions on the assistant's proposals in the period. Counts only; the text is not included."""

    proposals: int  # accepted + rejected
    accepted: int
    rejected: int
    edited_after: int  # a passage the assistant wrote, rewritten by the person afterwards


class Stats(BaseModel):
    generated_at: datetime
    days: int
    scope: StatsScope
    totals: Totals
    by_state: list[CountItem]
    by_type: list[CountItem]
    by_level: list[CountItem]
    by_tag: list[CountItem]
    by_issued_year: list[CountItem]
    by_unit: list[UnitCount]
    uploads_by_month: list[CountItem]  # last 12 months, key yyyy-mm
    questions_by_day: list[DayCount]
    usage_by_unit: list[UnitUsage]
    moderation_by_action: list[CountItem]
    moderation_recent: list[ModerationEvent]
    canvas: CanvasUsage
