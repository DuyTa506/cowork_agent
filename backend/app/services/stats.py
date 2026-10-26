"""Figures for the dashboard: what the document store holds and how the units use the system.

Scope: an administrator sees the whole organisation; a commander the subtree of their own unit. The numbers are counts only (no
document text, no message text), so they are not limited by secrecy level the way a document list is.

Time series are bucketed in Python in Vietnam time (UTC+7, no daylight saving) so that SQLite and Postgres give the same answer;
the categorical counts are grouped in SQL on labelled expressions (Postgres refuses the same expression repeated with new bind
parameters, see `tagging.facets`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.models import AuditLog, Document, DocumentState, DocumentTag, DraftRevision, User
from app.models.base import now_utc
from app.services import organization

VIETNAM = timezone(timedelta(hours=7))
PERIODS = (7, 30, 90)
STATE_LABELS = {"ready": "Sẵn sàng", "needs_review": "Cần xem lại", "needs_ocr": "Cần OCR", "failed": "Không đọc được",
                "uploaded": "Chờ xử lý", "processing": "Đang xử lý"}
LEVEL_LABELS = {"thuong": "Thường", "mat": "Mật"}
ACTIVE_IGNORED = ("auth.login_failed",)
SCAN_TAG = "Bản scan (OCR)"
TOP_TYPES, TOP_TAGS, MODERATION_RECENT = 12, 15, 8


def require_viewer(user: User) -> None:
    """Dashboards are for administrators and commanders; staff and reviewers do not see unit-wide usage."""
    if user.role not in ("admin", "commander"):
        raise Forbidden("Trang thống kê chỉ dành cho quản trị viên và chỉ huy.")


def _local(moment: datetime) -> datetime:
    return moment.astimezone(VIETNAM)


def _days(until: date, count: int) -> list[date]:
    return [until - timedelta(days=count - 1 - i) for i in range(count)]


def _months(until: date, count: int) -> list[str]:
    out, year, month = [], until.year, until.month
    for _ in range(count):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out[::-1]


def build(db: Session, user: User, days: int = 30) -> dict:
    """The dashboard payload for `user` over the last `days` days (one of `PERIODS`)."""
    require_viewer(user)
    days = days if days in PERIODS else 30
    chart = organization.tree()
    everything = user.role == "admin"
    root = user.unit_id if user.unit_id in chart.units else ""
    unit_ids = set(chart.units) if everything else set(chart.subtree(root)) if root else set()

    def branch_of(unit_id: str) -> tuple[str, str]:
        """The top-level branch under the root that `unit_id` belongs to (a unit directly under the root is its own branch)."""
        path = chart.path_to(unit_id) if unit_id in chart.units else ()
        pick = path[1] if len(path) > 1 else (path[0] if path else "")
        return pick, chart.units[pick].name if pick in chart.units else ""

    def name_of(unit_id: str) -> str:
        return chart.units[unit_id].name if unit_id in chart.units else (unit_id or "Chưa rõ đơn vị")

    in_scope = Document.unit_id.in_(unit_ids) if unit_ids else Document.id < 0
    now = now_utc()
    today = _local(now).date()

    # ----- documents -----
    states = dict(db.execute(select(Document.state, func.count()).where(in_scope).group_by(Document.state)).all())
    levels = dict(db.execute(select(Document.level, func.count()).where(in_scope).group_by(Document.level)).all())
    kinds = db.execute(select(Document.document_type, func.count()).where(in_scope).group_by(Document.document_type)
                       .order_by(func.count().desc())).all()
    year = func.substr(Document.issued_date, 1, 4).label("year")
    issued = db.execute(select(year, func.count()).where(in_scope, Document.issued_date != "").group_by(year).order_by(year)).all()
    per_unit = db.execute(select(Document.unit_id, func.count()).where(in_scope).group_by(Document.unit_id)).all()
    tags = db.execute(select(DocumentTag.tag, func.count()).join(Document, Document.id == DocumentTag.document_id).where(in_scope)
                      .group_by(DocumentTag.tag).order_by(func.count().desc(), DocumentTag.tag).limit(TOP_TAGS + 12)).all()
    scanned = db.scalar(select(func.count()).select_from(DocumentTag).join(Document, Document.id == DocumentTag.document_id)
                        .where(in_scope, DocumentTag.tag == SCAN_TAG)) or 0
    chunks = db.scalar(select(func.coalesce(func.sum(Document.chunk_count), 0)).where(in_scope)) or 0
    uploaded = db.execute(select(Document.unit_id, Document.uploaded_at).where(in_scope, Document.uploaded_at >= now - timedelta(days=380))).all()

    total = sum(states.values())
    by_state = [{"key": k, "label": STATE_LABELS.get(k, k), "count": states[k]}
                for k in ("ready", "needs_review", "needs_ocr", "failed", "uploaded", "processing") if states.get(k)]
    by_type = [{"key": t or "-", "label": t or "Chưa nhận diện", "count": c} for t, c in kinds]
    if len(by_type) > TOP_TYPES:
        by_type = by_type[:TOP_TYPES - 1] + [{"key": "other", "label": "Loại khác", "count": sum(i["count"] for i in by_type[TOP_TYPES - 1:])}]
    by_unit = []
    for unit_id, count in sorted(per_unit, key=lambda row: -row[1]):
        branch_id, branch = branch_of(unit_id)
        by_unit.append({"unit_id": unit_id, "name": name_of(unit_id), "branch_id": branch_id, "branch": branch, "count": count})
    months = _months(today, 12)
    by_month = Counter(_local(moment).strftime("%Y-%m") for _, moment in uploaded)
    uploads_by_month = [{"key": m, "label": m, "count": by_month.get(m, 0)} for m in months]

    # ----- usage (audit trail joined to the people) -----
    since = now - timedelta(days=days)
    month_start = datetime(today.year, today.month, 1, tzinfo=VIETNAM)
    window = min(since, month_start)
    people = {u.id: u for u in db.scalars(select(User).where(User.unit_id.in_(unit_ids) if unit_ids else User.id < 0))}
    rows = db.execute(select(AuditLog.user_id, AuditLog.action, AuditLog.created_at)
                      .where(AuditLog.user_id.in_(list(people) or [-1]), AuditLog.created_at >= window)).all()
    days_axis = _days(today, days)
    position = {d: i for i, d in enumerate(days_axis)}
    questions_by_day = [0] * days
    unit_series: dict[str, list[int]] = defaultdict(lambda: [0] * days)
    unit_uploads: Counter = Counter()
    unit_questions: Counter = Counter()
    unit_moderation: Counter = Counter()
    unit_active: dict[str, set[int]] = defaultdict(set)
    moderation_actions: Counter = Counter()
    unit_uploads.update(unit for unit, moment in uploaded if moment >= since)  # from the documents themselves: imports leave no audit row
    recent: list[tuple[datetime, int, str]] = []
    month_questions = 0
    totals_active: set[int] = set()
    for user_id, action, created in rows:
        unit = people[user_id].unit_id
        local = _local(created)
        in_period = created >= since
        if action == "chat.ask":
            if local >= month_start:
                month_questions += 1
            if in_period and local.date() in position:
                questions_by_day[position[local.date()]] += 1
                unit_series[unit][position[local.date()]] += 1
                unit_questions[unit] += 1
        if not in_period:
            continue
        if action not in ACTIVE_IGNORED:
            unit_active[unit].add(user_id)
            totals_active.add(user_id)
        if action.startswith("moderation."):
            unit_moderation[unit] += 1
            moderation_actions[action.split(".", 1)[1]] += 1
            recent.append((created, user_id, action.split(".", 1)[1]))
    recent.sort(reverse=True)

    # ----- canvas proposals (counts only; the text of a revision is not part of the dashboard) -----
    in_units = DraftRevision.unit_id.in_(unit_ids) if unit_ids else DraftRevision.id < 0
    revisions = dict(db.execute(select(DraftRevision.outcome, func.count()).where(in_units, DraftRevision.created_at >= since)
                                .group_by(DraftRevision.outcome)).all())
    accepted, rejected = revisions.get("accepted", 0), revisions.get("rejected", 0)

    members: Counter = Counter(u.unit_id for u in people.values())  # every account, so 'active of total' never exceeds the total
    usage = []
    for unit in sorted(unit_ids, key=lambda u: chart.path_to(u)) if unit_ids else []:
        if not (members[unit] or unit_questions[unit] or unit_uploads[unit] or unit_moderation[unit]):
            continue
        branch_id, branch = branch_of(unit)
        usage.append({"unit_id": unit, "name": name_of(unit), "branch_id": branch_id, "branch": branch, "users": members[unit],
                      "active_users": len(unit_active[unit]), "questions": unit_questions[unit], "uploads": unit_uploads[unit],
                      "moderation": unit_moderation[unit], "series": unit_series[unit] if unit in unit_series else [0] * days})

    return {
        "generated_at": now, "days": days,
        "scope": {"unit_id": root, "unit_name": name_of(root) if root else "", "everything": everything},
        "totals": {"documents": total, "ready": states.get("ready", 0), "needs_review": states.get("needs_review", 0),
                   "needs_ocr": states.get("needs_ocr", 0), "failed": states.get("failed", 0),
                   "processing": states.get("uploaded", 0) + states.get("processing", 0), "secret": levels.get("mat", 0),
                   "scanned": scanned, "chunks": int(chunks), "users": sum(members.values()), "active_users": len(totals_active),
                   "questions_period": sum(questions_by_day), "questions_month": month_questions,
                   "uploads_period": sum(unit_uploads.values()), "moderation_period": sum(unit_moderation.values())},
        "by_state": by_state, "by_type": by_type,
        "by_level": [{"key": k, "label": LEVEL_LABELS.get(k, k), "count": levels[k]} for k in ("thuong", "mat") if levels.get(k)],
        "by_tag": [{"key": t, "label": t, "count": c} for t, c in tags if not t.startswith("Năm ") and t != SCAN_TAG][:TOP_TAGS],
        "by_issued_year": [{"key": y, "label": y, "count": c} for y, c in issued],
        "by_unit": by_unit, "uploads_by_month": uploads_by_month,
        "questions_by_day": [{"day": d.isoformat(), "count": questions_by_day[i]} for i, d in enumerate(days_axis)],
        "usage_by_unit": usage,
        "moderation_by_action": [{"key": k, "label": {"block": "Bị chặn", "warn": "Cảnh báo", "log": "Chỉ ghi nhận"}[k], "count": moderation_actions[k]}
                                 for k in ("block", "warn", "log") if moderation_actions[k]],
        "moderation_recent": [{"at": at, "username": people[uid].username, "unit_name": name_of(people[uid].unit_id), "action": action}
                              for at, uid, action in recent[:MODERATION_RECENT]],
        "canvas": {"proposals": accepted + rejected, "accepted": accepted, "rejected": rejected,
                   "edited_after": revisions.get("edited_after", 0)},
    }
