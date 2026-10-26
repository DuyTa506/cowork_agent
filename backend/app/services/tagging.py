"""Labels on documents: computed ones (year, topic, scanned) and hand-made ones, and the counts the filter panel shows."""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models import Document, DocumentTag, User

from .documents import readable_clause

MAX_MANUAL = 12
MAX_LENGTH = 40

# Topic -> words that signal it. A topic is tagged when a word is in the title, or three or more occurrences are in the opening text.
TOPICS: dict[str, tuple[str, ...]] = {
    "Huấn luyện": ("huấn luyện", "tập huấn", "đào tạo", "bồi dưỡng", "quân huấn"),
    "Diễn tập": ("diễn tập", "thực binh"),
    "Sẵn sàng chiến đấu": ("sẵn sàng chiến đấu", "trực ban", "trực chiến", "tác chiến", "phòng thủ"),
    "Tổ chức, biên chế": ("biên chế", "kiện toàn", "tổ chức bộ máy", "thành lập", "sáp nhập", "giải thể"),
    "Cán bộ, quân lực": ("cán bộ", "quân lực", "bổ nhiệm", "điều động", "nghỉ hưu", "tuyển quân", "nhập ngũ", "quy hoạch"),
    "Chính sách": ("chính sách", "chế độ", "phụ cấp", "trợ cấp", "bảo hiểm", "khen thưởng", "thi đua", "kỷ luật"),
    "Tài chính": ("kinh phí", "ngân sách", "tài chính", "quyết toán", "dự toán", "mua sắm", "thanh toán"),
    "Hậu cần, kỹ thuật": ("hậu cần", "kỹ thuật", "quân nhu", "quân khí", "xăng dầu", "vận tải", "doanh trại", "quân y", "trang bị"),
    "Công nghệ thông tin": ("công nghệ thông tin", "thông tin liên lạc", "an toàn thông tin", "mạng máy tính", "cơ yếu", "bảo mật"),
    "Chính trị, tư tưởng": ("chính trị", "tư tưởng", "tuyên huấn", "dân vận", "đảng ủy", "đại hội", "nghị quyết"),
    "An ninh, bảo vệ": ("bảo vệ an ninh", "an ninh", "bảo vệ chính trị nội bộ", "bí mật nhà nước", "điều tra", "thi hành án"),
    "Công binh, xây dựng": ("công binh", "xây dựng", "công trình", "đường", "cầu", "rà phá bom mìn", "khắc phục hậu quả"),
    "Phòng không, không quân": ("phòng không", "không quân", "radar", "tên lửa"),
    "Dân quân tự vệ": ("dân quân", "tự vệ", "dự bị động viên", "động viên"),
    "Khoa học, quân sự": ("khoa học quân sự", "sáng kiến", "nghiên cứu", "đề tài"),
    "Kiểm tra, thanh tra": ("thanh tra", "kiểm tra", "giám sát", "kiểm toán", "khiếu nại", "tố cáo"),
    "Phòng chống thiên tai": ("thiên tai", "bão", "lũ", "cứu hộ", "cứu nạn", "tìm kiếm"),
}
_TOPIC_PATTERNS = {topic: [re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)") for word in words] for topic, words in TOPICS.items()}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def auto_tags(*, title: str, issued_date: str, head: str, scanned: bool, draft: bool = False) -> list[str]:
    """Year, topics, "Bản nháp" (no number and no date yet) and "Bản scan (OCR)" for a document, from its title, issue date and opening text.

    `issued_date` may be partial ("2026-01", "2026"): a draft knows its year before it has a day."""
    tags: list[str] = []
    if re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", issued_date or ""):
        tags.append(f"Năm {issued_date[:4]}")
    title_l, head_l = _fold(title), _fold(head[:2500])
    scored: list[tuple[int, str]] = []
    for topic, patterns in _TOPIC_PATTERNS.items():
        in_title = sum(1 for pattern in patterns if pattern.search(title_l))
        in_head = sum(len(pattern.findall(head_l)) for pattern in patterns)
        if in_title or in_head >= 3:
            scored.append((in_title * 5 + in_head, topic))
    tags += [topic for _, topic in sorted(scored, reverse=True)[:3]]  # the three strongest: more would stop being a filter
    if draft:
        tags.append("Bản nháp")
    if scanned:
        tags.append("Bản scan (OCR)")
    return tags


def clean(tags: list[str]) -> list[str]:
    """Tidy hand-typed tags: trimmed, single-spaced, no duplicates (case-insensitive), bounded in count and length.

    Raises:
        ValidationFailed: too many tags, or one is too long.
    """
    seen: dict[str, str] = {}
    for raw in tags:
        tag = re.sub(r"\s+", " ", raw.replace(",", " ")).strip()
        if not tag:
            continue
        if len(tag) > MAX_LENGTH:
            raise ValidationFailed(f"Thẻ dài quá {MAX_LENGTH} ký tự: “{tag[:20]}…”.")
        seen.setdefault(_fold(tag), tag)
    if len(seen) > MAX_MANUAL:
        raise ValidationFailed(f"Mỗi văn bản chỉ gắn tối đa {MAX_MANUAL} thẻ do người dùng đặt.")
    return list(seen.values())


def replace_auto(db: Session, document_id: int, tags: list[str]) -> None:
    """Sets the computed tags of a document (hand-made ones are kept; a tag already set by hand is not duplicated)."""
    db.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id, DocumentTag.source == "auto"))
    have = {t.lower() for t in db.scalars(select(DocumentTag.tag).where(DocumentTag.document_id == document_id))}
    for tag in tags:
        if tag.lower() not in have:
            db.add(DocumentTag(document_id=document_id, tag=tag, source="auto"))
            have.add(tag.lower())
    db.flush()


def set_manual(db: Session, document_id: int, tags: list[str]) -> list[str]:
    """Replaces the hand-made tags of a document; returns all its tags afterwards."""
    tags = clean(tags)
    db.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id, DocumentTag.source == "manual"))
    auto = {t.lower() for t in db.scalars(select(DocumentTag.tag).where(DocumentTag.document_id == document_id, DocumentTag.source == "auto"))}
    for tag in tags:
        if tag.lower() not in auto:
            db.add(DocumentTag(document_id=document_id, tag=tag, source="manual"))
    db.flush()
    return tags_of(db, [document_id]).get(document_id, [])


def remove_all(db: Session, document_id: int) -> None:
    db.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))


def manual_of(db: Session, document_id: int) -> list[str]:
    """The hand-made tags of one document."""
    return list(db.scalars(select(DocumentTag.tag).where(DocumentTag.document_id == document_id, DocumentTag.source == "manual").order_by(DocumentTag.tag)))


def tags_of(db: Session, ids: list[int]) -> dict[int, list[str]]:
    """Tags of each document (computed first, then hand-made), in one query."""
    if not ids:
        return {}
    out: dict[int, list[str]] = {i: [] for i in ids}
    rows = db.execute(select(DocumentTag.document_id, DocumentTag.tag, DocumentTag.source).where(DocumentTag.document_id.in_(ids))
                      .order_by(DocumentTag.source, DocumentTag.tag)).all()
    for document_id, tag, _ in rows:
        out[document_id].append(tag)
    return out


def facets(db: Session, user: User, limit: int = 60) -> dict[str, list[dict]]:
    """What a person can filter by and how many documents each choice has: units (documents directly in each), types, years and the most used tags (readable documents only)."""
    readable = readable_clause(user)
    types = db.execute(select(Document.document_type, func.count()).where(readable, Document.document_type != "")
                       .group_by(Document.document_type).order_by(func.count().desc())).all()
    year = func.substr(Document.issued_date, 1, 4).label("year")  # one labelled expression: Postgres rejects the same call repeated with new bind parameters
    years = db.execute(select(year, func.count()).where(readable, Document.issued_date != "").group_by(year).order_by(year.desc())).all()
    tags = db.execute(select(DocumentTag.tag, func.count()).join(Document, Document.id == DocumentTag.document_id).where(readable)
                      .group_by(DocumentTag.tag).order_by(func.count().desc(), DocumentTag.tag).limit(limit)).all()
    units = db.execute(select(Document.unit_id, func.count()).where(readable).group_by(Document.unit_id)).all()
    return {"units": [{"value": v, "count": c} for v, c in units], "types": [{"value": v, "count": c} for v, c in types], "years": [{"value": v, "count": c} for v, c in years],
            "tags": [{"value": v, "count": c} for v, c in tags]}
