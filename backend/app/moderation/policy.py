"""What the system does with a message the rules object to: warn or block, and always leave a trace."""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ContentBlocked
from app.models import AuditLog, User
from app.models.base import now_utc
from app.services import audit, settings

from . import model
from .check import CATEGORY_LABELS, Hit, Verdict, check

log = logging.getLogger(__name__)
WINDOW = timedelta(days=30)  # how far back "this is your Nth time" looks
ACTIONS = {"mild": "mild_action", "severe": "severe_action"}


def _earlier(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.user_id == user.id, AuditLog.action.like("moderation.%"), AuditLog.created_at >= now_utc() - WINDOW)) or 0


# Ordinary service vocabulary the classifier takes for an insult ("con chó nghiệp vụ" scores 0.98 HATE); it is removed before the model reads the text.
_SERVICE_TERMS = re.compile(r"chó\s+(nghiệp\s+vụ|béc[\s-]?giê|săn|đánh\s+hơi|trinh\s+sát)", re.IGNORECASE)


def _ask_model(verdict: Verdict, text: str, threshold: float) -> None:
    """Adds the classifier's finding, if it is confident, as a mild hit (it catches insults that use none of the listed words)."""
    classifier = model.get()
    if classifier is None:
        return
    try:
        (scores,) = classifier.scores([_SERVICE_TERMS.sub("khuyển", text)])
    except Exception:  # noqa: BLE001  (the rules still stand when the model fails)
        log.exception("moderation: the classifier failed")
        return
    if scores.toxic >= threshold and scores.label != "CLEAN":
        category = "ky_thi" if scores.label == "HATE" else "xuc_pham"
        verdict.hits.append(Hit(f"model:{scores.label} {scores.toxic:.2f}", category, "nhe", " ".join(text.split())[:80]))


def screen(db: Session, user: User, *, text: str, entity_id: str, ip: str = "") -> dict[str, Any] | None:
    """Checks a message a person is sending to the assistant.

    The finding is written to the audit trail (who, when, from where, which conversation, what matched and a short excerpt) and
    committed, so it is kept even when the message is refused.

    Returns:
        ``None`` for an ordinary message, or the notice the screen shows (``{"level", "action", "categories", "message", "count"}``)
        when the message is let through with a warning (or only logged: the notice then has ``action == "log"`` and is not shown).

    Raises:
        ContentBlocked: the administrator's policy refuses this message.
    """
    values = settings.load(db, "moderation")
    if not values["enabled"]:
        return None
    verdict: Verdict = check(text)
    if values["model_enabled"] and verdict.level != "severe":
        _ask_model(verdict, text, float(values["model_threshold"]))
    if verdict.level == "none":
        return None
    action = values[ACTIONS[verdict.level]]
    earlier = _earlier(db, user)
    labels = ", ".join(CATEGORY_LABELS[c] for c in verdict.categories)
    terms = "; ".join(f"{h.term} ({h.severity})" for h in verdict.hits)
    excerpt = verdict.hits[0].excerpt
    audit.record(db, user, f"moderation.{action}", entity_type="chat", entity_id=entity_id, ip=ip,
                 detail=f"{verdict.level}: {labels}. Khớp: {terms}. Trích: …{excerpt}…. Lần thứ {earlier + 1} trong 30 ngày.")
    db.commit()
    message = (f"Tin nhắn có nội dung {labels}. Hệ thống đã ghi nhận tài khoản {user.username} (lần thứ {earlier + 1} trong 30 ngày) "
               "để quản trị viên xem xét. Vui lòng dùng ngôn ngữ đúng mực khi làm việc trên hệ thống.")
    if action == "block":
        raise ContentBlocked(message + " Tin nhắn chưa được gửi.")
    return {"level": verdict.level, "action": action, "categories": verdict.categories, "message": message, "count": earlier + 1}
