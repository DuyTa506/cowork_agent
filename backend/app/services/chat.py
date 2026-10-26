"""Conversations with the assistant: sessions, messages, and running a turn.

A turn is the user's message and everything the assistant does about it. It runs in a background thread that owns its database
session and persists the outcome itself, so closing the browser mid-answer does not lose the answer; the HTTP response only
relays the thread's events (see `Turn.events`). Citations are resolved here, against the database and with the asker's own
permissions, because the model only knows document ids.
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agent import history
from app.agent.translate import Translator
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.drafting import style, templates
from app.models import AttachmentState, ChatAttachment, ChatMessage, ChatSession, Document, Draft, User
from app.models.base import now_utc

from . import attachments, documents, drafts, organization, settings

if TYPE_CHECKING:  # the harness SDK is only needed where a turn runs (the web process), not in the worker
    from app.agent.runtime import AgentPool

log = logging.getLogger(__name__)

DEFAULT_TITLE = "Cuộc trò chuyện mới"
TITLE_CHARS = 48
MAX_TEXT = 8000
HEARTBEAT_SECONDS = 15.0
SessionFactory = Callable[[], Session]


# --------------------------------------------------------------------------------------------------------------------------
# sessions and messages
# --------------------------------------------------------------------------------------------------------------------------
def new_id() -> str:
    """Identifier of a conversation (also the harness session id and the attachment scope)."""
    import uuid
    return uuid.uuid4().hex


def list_sessions(db: Session, user: User) -> list[ChatSession]:
    """The user's conversations, most recently active first."""
    return list(db.scalars(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc())))


def get(db: Session, user: User, session_id: str) -> ChatSession:
    """The user's own conversation; other people's look like unknown ones."""
    row = db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id))
    if row is None:
        raise NotFound("Không tìm thấy cuộc trò chuyện.")
    return row


def create(db: Session, user: User, title: str = "") -> ChatSession:
    """Starts an empty conversation."""
    row = ChatSession(id=new_id(), user_id=user.id, title=(title.strip() or DEFAULT_TITLE)[:200])
    db.add(row)
    db.flush()
    return row


def rename(db: Session, row: ChatSession, title: str) -> ChatSession:
    """Renames a conversation."""
    title = title.strip()
    if not title:
        raise ValidationFailed("Tiêu đề không được để trống.")
    row.title = title[:200]
    return row


def messages(db: Session, session_id: str) -> list[ChatMessage]:
    """The messages of a conversation in order."""
    return list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)))


def delete_session(db: Session, pool: "AgentPool | None", row: ChatSession) -> None:
    """Removes a conversation with its messages, attached files and draft; stops its agent."""
    if pool is not None:
        pool.stop(row.id)
    for attachment in attachments.list_for(db, row.id):
        attachments.delete(db, attachment)
    attachments.delete_session_files(row.id)
    history.remove(row.id)
    drafts.delete(db, row.id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id == row.id))
    db.delete(row)


def purge_idle(db: Session, pool: "AgentPool | None") -> int:
    """Deletes conversations idle longer than the configured retention; returns how many."""
    days = int(settings.load(db, "storage")["chat_retention_days"])
    stale = list(db.scalars(select(ChatSession).where(ChatSession.updated_at < now_utc() - timedelta(days=days))))
    for row in stale:
        delete_session(db, pool, row)
    if stale:
        db.commit()
    return len(stale)


def title_from(text: str) -> str:
    """A conversation title from its first message."""
    line = " ".join(text.split())
    return line if len(line) <= TITLE_CHARS else line[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------------------------------------------------------
def resolve_citations(db: Session, user: User, session_id: str, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adds what the screen shows for each citation (title, number/symbol, date, unit) from the database.

    A store document the user can no longer read is returned without details and with ``readable: false``.
    """
    store_ids = [int(c["doc_id"]) for c in raw if str(c["doc_id"]).isdigit()]
    found: dict[int, Document] = {}
    if store_ids:
        found = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(store_ids), documents.readable_clause(user)))}
    files = {f"att{a.id}": a for a in attachments.list_for(db, session_id)}
    units = organization.tree().units
    out: list[dict[str, Any]] = []
    for item in raw:
        doc_id = str(item["doc_id"])
        base = {"n": item["n"], "doc_id": doc_id, "section": item["section"], "text": item["text"], "pi": item["pi"]}
        if doc_id in files:
            att = files[doc_id]
            out.append({**base, "kind": "attachment", "title": att.title or att.name, "ref": "", "doc_type": att.document_type, "date": "",
                        "unit_name": "", "readable": True})
        elif doc_id.isdigit() and int(doc_id) in found:
            doc = found[int(doc_id)]
            ref = f"{doc.document_number}/{doc.symbol}".strip("/")
            out.append({**base, "kind": "store", "title": doc.title or doc.original_name, "ref": ref, "doc_type": doc.document_type,
                        "date": doc.issued_date, "unit_name": units[doc.unit_id].name if doc.unit_id in units else doc.unit_id,
                        "readable": True})
        else:
            out.append({**base, "kind": "store", "title": "Văn bản không còn truy cập được", "ref": "", "doc_type": "", "date": "",
                        "unit_name": "", "readable": False, "text": "", "pi": [-1, -1]})
    return out


# --------------------------------------------------------------------------------------------------------------------------
# a turn
# --------------------------------------------------------------------------------------------------------------------------
@dataclass
class Turn:
    """One user message being answered. Created by `prepare`, run by `start`."""

    session_id: str
    user_id: int
    user_message_id: int
    title: str
    text: str
    attachment_ids: list[int]
    canvas: bool
    context: dict[str, str]
    resume: bool
    factory: SessionFactory
    pool: "AgentPool"
    notice: dict[str, Any] | None = None  # what the input screening has to tell the person (shown before the answer)
    stopped: threading.Event = field(default_factory=threading.Event)
    _events: "queue.Queue[tuple[str, Any] | None]" = field(default_factory=queue.Queue)

    # ----- what the HTTP response relays -----
    def events(self) -> Iterator[tuple[str, dict[str, Any]] | None]:
        """Yields ``(event name, data)`` until the turn ends; ``None`` every few seconds while quiet (keep-alive).

        Abandoning the iterator (the client went away) does not stop the turn.
        """
        yield "session", {"session_id": self.session_id, "user_message_id": self.user_message_id, "title": self.title}
        if self.notice:
            yield "moderation", self.notice
        while True:
            try:
                item = self._events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                yield None
                continue
            if item is None:
                return
            yield item

    def _emit(self, name: str, data: dict[str, Any]) -> None:
        self._events.put((name, data))

    def start(self) -> None:
        """Runs the turn in a background thread."""
        threading.Thread(target=self._run, name=f"turn-{self.session_id[:8]}", daemon=True).start()

    def stop(self) -> None:
        """Interrupts the turn; the partial work is saved as a stopped answer."""
        self.stopped.set()
        self.pool.stop(self.session_id)

    # ----- the work -----
    def _run(self) -> None:
        from app.agent.runtime import AgentUnavailable

        translator = Translator()
        status, failure, runtime = "done", "", None
        try:
            with self.factory() as db:
                user = db.get(User, self.user_id)
                values = settings.load(db, "llm")
                prompt = self._prompt(db)
            runtime = self.pool.acquire(self.session_id, principal=organization.principal_of(user), user=user.username,
                                        user_id=user.id, llm=values, resume=self.resume)
            try:
                if not self.stopped.is_set():  # a stop pressed while the agent was still starting
                    runtime.run(prompt, lambda event: self._relay(translator, event))
            finally:
                self.pool.release(runtime)
            if translator.failure and not translator.answer:
                status, failure = "error", _friendly(translator.failure)
        except AgentUnavailable as exc:
            status, failure = "error", exc.message
        except Conflict as exc:
            status, failure = "error", exc.message
        except Exception as exc:  # noqa: BLE001  (harness crash, model unreachable...)
            if self.stopped.is_set():
                status = "stopped"
            else:
                log.exception("turn failed in %s", self.session_id)
                status, failure = "error", _friendly(f"{type(exc).__name__}: {exc}")
        finally:
            _release(self.session_id)
        if self.stopped.is_set():
            status, failure = "stopped", ""
        self._finish(translator, status, failure)

    def _relay(self, translator: Translator, event: dict[str, Any]) -> None:
        """Folds a runtime event and forwards what the screen should show."""
        for ui in translator.feed(event):
            if ui["type"] == "step":
                self._emit("step", {"step": ui["step"]})
        if translator.canvas_changed:
            translator.canvas_changed = False
            with self.factory() as db:
                draft = drafts.snapshot(db, self.session_id)
            if draft is not None:
                self._emit("canvas", {"draft": _jsonable(draft)})

    def _finish(self, translator: Translator, status: str, failure: str) -> None:
        """Persists the assistant's message and tells the client how the turn ended."""
        text, cites = translator.finish()
        if status == "done" and not text.strip():
            status, failure = "error", "Trợ lý không đưa ra được câu trả lời. Hãy thử hỏi lại hoặc diễn đạt khác."
        try:
            with self.factory() as db:
                user = db.get(User, self.user_id)
                citations = resolve_citations(db, user, self.session_id, cites) if cites else []
                message = ChatMessage(session_id=self.session_id, role="assistant", content=text if status == "done" else failure,
                                      steps=[s.as_dict() for s in translator.steps], citations=citations, status=status)
                db.add(message)
                session = db.get(ChatSession, self.session_id)
                if session is not None:
                    session.updated_at = now_utc()
                db.commit()
                message_id = message.id
            if status == "error":
                self._emit("error", {"message": failure})
            elif status == "done":
                self._emit("answer", {"text": text, "citations": citations})
            self._emit("done", {"message_id": message_id, "title": self.title, "status": status})
        except Exception:  # noqa: BLE001
            log.exception("saving the answer of %s", self.session_id)
            self._emit("error", {"message": "Không lưu được câu trả lời."})
        finally:
            self._events.put(None)

    def _prompt(self, db: Session) -> str:
        """The text sent to the model: the message plus facts the tools cannot tell it (attachments, canvas, selection)."""
        notes: list[str] = []
        if self.attachment_ids:
            rows = db.scalars(select(ChatAttachment).where(ChatAttachment.id.in_(self.attachment_ids))).all()
            notes.append("Tệp người dùng đính kèm ở lượt này: " + "; ".join(
                f'{attachments.doc_id(a.id)} "{a.name}"{f" ({a.document_type})" if a.document_type else ""}' for a in rows))
        if self.canvas:
            notes.append("Người dùng đã bật Canvas: soạn văn bản vào canvas bằng các công cụ canvas_*, theo văn phong của đơn vị "
                         "người dùng (canvas_style).")
        draft = drafts.find(db, self.session_id)
        picked = style.choice(draft.style) if draft is not None else None
        if draft is not None and self.context.get("block_id"):
            selected = self.context.get("selection", "")
            notes.append(f"Người dùng đang chọn đoạn {self.context['block_id']} của bản dự thảo"
                         + (f': "{selected}"' if selected else "") + "; yêu cầu áp dụng cho đoạn đó (dùng canvas_edit_block).")
            if self.context.get("action") == "military":
                notes.append("Đổi văn phong đoạn đã chọn theo hướng dẫn dưới đây; giữ nguyên nội dung, số liệu, tên riêng, ngày tháng "
                             "của đoạn gốc, không thêm thông tin mới.\n"
                             + style.prompt_note(organization.tree(), drafts.unit_of(db, draft), templates.get(draft.template),
                                                 choice=picked))
            elif picked and not style.is_default(picked):
                notes.append(style.choice_note(picked))
        elif draft is not None:
            notes.append("Cuộc trò chuyện đang có bản dự thảo. Gọi công cụ canvas_read trước khi sửa; không viết lại lệnh đó bằng chữ.")
            if picked and not style.is_default(picked):
                notes.append(style.choice_note(picked))
        return self.text if not notes else self.text + "\n\n" + "\n".join(f"[Ghi chú hệ thống] {n}" for n in notes)


_ACTIVE: dict[str, Turn] = {}
_ACTIVE_LOCK = threading.Lock()


def _reserve(session_id: str) -> None:
    """Marks a conversation as answering; `Conflict` when it already is (check and mark are one step, so two requests cannot both pass)."""
    with _ACTIVE_LOCK:
        if session_id in _ACTIVE:
            raise Conflict("Cuộc trò chuyện đang trả lời, hãy đợi hoặc bấm dừng.")
        _ACTIVE[session_id] = None  # type: ignore[assignment]  (filled in by `prepare` once the turn exists)


def _release(session_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.pop(session_id, None)


def has_history(db: Session, session_id: str) -> bool:
    """Whether the agent has already answered in this conversation (so its harness session can be resumed)."""
    return bool(db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant",
                                                                   ChatMessage.status != "error")))


def warm_up(factory: SessionFactory, pool: "AgentPool", user_id: int, session_id: str) -> None:
    """Starts the conversation's agent in the background so the first answer does not wait for it (about ten seconds).

    Harmless when it is already running, busy or cannot start: the first real message then reports the problem.
    """
    def work() -> None:
        try:
            with factory() as db:
                user, values, resume = db.get(User, user_id), settings.load(db, "llm"), has_history(db, session_id)
            runtime = pool.acquire(session_id, principal=organization.principal_of(user), user=user.username, user_id=user.id, llm=values,
                                   resume=resume)
            pool.release(runtime)
        except Exception as exc:  # noqa: BLE001
            log.info("warm-up of %s skipped: %s", session_id, exc)

    threading.Thread(target=work, name=f"warm-{session_id[:8]}", daemon=True).start()


def active_turn(session_id: str) -> Turn | None:
    """The turn currently answering in a conversation, if any."""
    return _ACTIVE.get(session_id)


def _friendly(raw: str) -> str:
    """A short Vietnamese message for a failure (details stay in the log)."""
    log.warning("agent failure: %s", raw[:300])
    lowered = raw.lower()
    if any(w in lowered for w in ("connect", "timed out", "timeout", "unreachable", "refused", "econn")):
        return "Không kết nối được mô hình hội thoại. Kiểm tra máy chủ mô hình trong Quản trị → Hệ thống."
    return "Trợ lý gặp lỗi khi xử lý yêu cầu. Hãy thử lại; nếu lặp lại, báo quản trị viên."


def _jsonable(value: Any) -> Any:
    """Converts datetimes inside a view to ISO strings so it can be sent as JSON."""
    from datetime import datetime
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def prepare(db: Session, user: User, session: ChatSession, *, text: str, attachment_ids: list[int], canvas: bool,
            context: dict[str, str] | None, factory: SessionFactory, pool: "AgentPool") -> Turn:
    """Validates a message, stores it and returns the turn to start.

    Raises:
        ValidationFailed: empty or too long, or an attachment that is not this conversation's or not ready yet.
        Conflict: the conversation is still answering the previous message.
    """
    text = text.strip()
    if not text:
        raise ValidationFailed("Tin nhắn trống.")
    if len(text) > MAX_TEXT:
        raise ValidationFailed(f"Tin nhắn quá dài (tối đa {MAX_TEXT} ký tự).")
    _reserve(session.id)
    try:
        return _store_message(db, user, session, text, attachment_ids, canvas, context, factory, pool)
    except BaseException:
        _release(session.id)
        raise


def _store_message(db: Session, user: User, session: ChatSession, text: str, attachment_ids: list[int], canvas: bool,
                   context: dict[str, str] | None, factory: SessionFactory, pool: "AgentPool") -> Turn:
    """The checks and writes of `prepare`, run while the conversation is reserved."""
    wanted = list(dict.fromkeys(attachment_ids))
    if wanted:
        rows = db.scalars(select(ChatAttachment).where(ChatAttachment.id.in_(wanted), ChatAttachment.session_id == session.id)).all()
        if len(rows) != len(wanted):
            raise ValidationFailed("Có tệp đính kèm không thuộc cuộc trò chuyện này.")
        waiting = [a.name for a in rows if a.state != AttachmentState.READY]
        if waiting:
            raise ValidationFailed("Tệp chưa xử lý xong hoặc bị lỗi: " + ", ".join(waiting))
    count = db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)) or 0
    resume = has_history(db, session.id)
    message = ChatMessage(session_id=session.id, role="user", content=text, attachment_ids=wanted)
    db.add(message)
    if count == 0 or session.title == DEFAULT_TITLE:
        session.title = title_from(text)
    session.updated_at = now_utc()
    db.commit()
    turn = Turn(session.id, user.id, message.id, session.title, text, wanted, canvas, dict(context or {}), resume, factory, pool)
    _ACTIVE[session.id] = turn
    return turn
