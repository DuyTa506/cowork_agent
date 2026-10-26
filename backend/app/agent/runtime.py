"""Agent runtimes: one DeepSeek Harness process per conversation, kept warm between messages.

Why one per conversation: the tool processes it starts are bound to a single caller and conversation by a signed token in their
environment (`app.rag.identity`), which the model cannot change. A conversation's history is persisted by the harness under
``DATA_DIR/dsh``; when a runtime is evicted (idle, or the pool is full) the next message starts a new one that resumes it.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deepseek_harness import DeepSeekHarness, Notification, Session

from app.agent import history
from app.core import config
from app.core.errors import Conflict, ServiceUnavailable
from app.org import Principal
from app.rag import identity

log = logging.getLogger(__name__)

PATCH = Path(__file__).with_name("qk3.patch.yml")
BACKEND = Path(__file__).resolve().parents[2]
# Variables the tool process needs from this process; the profile patch forwards exactly these (empty when unset).
FORWARDED = ("JWT_SECRET", "SETTINGS_KEY", "DATABASE_URL", "DATA_DIR", "UPLOAD_DIR", "TEMP_DIR", "APP_ENV", "QDRANT_URL",
             "QDRANT_API_KEY", "QDRANT_COLLECTION", "QK3_EMBEDDER", "QK3_EMBEDDER_DIM")
Callback = Callable[[dict[str, Any]], None]


def reasoning_effort(llm: dict[str, Any]) -> str:
    """The effort the harness should request for this model configuration.

    The qk3 profile uses pi-ai's ``qwen-chat-template``: any effort other than ``off`` sends
    ``chat_template_kwargs.enable_thinking: true``, and ``off`` sends false. Qwen3 thinks unless that
    flag is sent, so the admin switch has to be forwarded on every start.

    Args:
        llm: The ``llm`` settings section.

    Returns:
        ``high`` when thinking is on (the default), ``off`` when the administrator turned it off.
    """
    return "high" if llm.get("thinking", True) else "off"


class AgentUnavailable(ServiceUnavailable):
    """The chat model is not configured or the agent could not start."""


@dataclass
class Runtime:
    """A running harness bound to one conversation."""

    session_id: str
    key: tuple
    harness: DeepSeekHarness
    session: Session
    busy: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.monotonic)

    def run(self, content: "str | list[dict[str, Any]]", on_event: Callback) -> None:
        """Runs one turn, calling `on_event` with every session event (blocking until the turn ends)."""
        def forward(notification: Notification) -> None:
            if notification.method == "session.event":
                event = notification.payload.get("event")
                if isinstance(event, dict) and notification.payload.get("sessionId") == self.session_id:
                    on_event(event)

        self.session.run(content, on_notification=forward)
        self.last_used = time.monotonic()

    def close(self) -> None:
        """Stops the harness process (also interrupts a running turn)."""
        try:
            self.harness.close()
        except Exception:  # noqa: BLE001
            log.exception("closing runtime of %s", self.session_id)


class AgentPool:
    """Keeps at most `max_runtimes` conversations' runtimes alive and drops idle ones after `idle_seconds`.

    Args:
        env: Extra environment for the runtimes (tests point them at a temporary database and index).
    """

    def __init__(self, max_runtimes: int = 16, idle_seconds: float = 900.0, env: dict[str, str] | None = None):
        self.max_runtimes, self.idle_seconds, self.env = max_runtimes, idle_seconds, env or {}
        self._runtimes: dict[str, Runtime] = {}
        self._start_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    # ----- lifecycle -----
    def acquire(self, session_id: str, *, principal: Principal, user: str, user_id: int, llm: dict[str, Any], resume: bool) -> Runtime:
        """The runtime of a conversation, started (or restarted when the caller's identity or the model settings changed).

        Starting takes several seconds, so it happens outside the pool lock: other conversations are not held up by it.

        Raises:
            AgentUnavailable: no model configured, the pool is full of busy runtimes, or the harness failed to start.
            Conflict: the conversation is already answering.
        """
        if not (llm.get("base_url") and llm.get("model")):
            raise AgentUnavailable("Chưa cấu hình mô hình hội thoại (Quản trị → Hệ thống → LLM).")
        key = (principal.unit_id, principal.role, user_id, tuple(sorted((k, str(v)) for k, v in llm.items())))
        with self._starting(session_id):
            with self._lock:
                to_close = self._evict_idle()
                current = self._runtimes.get(session_id)
                if current is not None and current.key != key and not current.busy.locked():
                    del self._runtimes[session_id]
                    to_close.append(current)
                    current = None
                if current is None and len(self._runtimes) >= self.max_runtimes:
                    freed = self._evict_one()
                    if freed is None:
                        for runtime in to_close:
                            runtime.close()
                        raise AgentUnavailable("Hệ thống đang bận phục vụ nhiều cuộc trò chuyện, thử lại sau ít phút.")
                    to_close.append(freed)
            for runtime in to_close:
                runtime.close()
            if current is None:
                current = self._start(session_id, key, principal, user, user_id, llm, resume)
                with self._lock:
                    self._runtimes[session_id] = current
        if not current.busy.acquire(blocking=False):
            raise Conflict("Cuộc trò chuyện đang trả lời, hãy đợi hoặc bấm dừng.")
        return current

    def release(self, runtime: Runtime) -> None:
        """Marks the runtime idle again."""
        runtime.last_used = time.monotonic()
        if runtime.busy.locked():
            runtime.busy.release()

    def stop(self, session_id: str) -> bool:
        """Kills the conversation's runtime (interrupting its turn); returns whether there was one."""
        with self._lock:
            runtime = self._runtimes.pop(session_id, None)
            self._start_locks.pop(session_id, None)
        if runtime is not None:
            runtime.close()
        return runtime is not None

    def close_all(self) -> None:
        """Stops every runtime (application shutdown)."""
        with self._lock:
            runtimes, self._runtimes = list(self._runtimes.values()), {}
        for runtime in runtimes:
            runtime.close()

    def _starting(self, session_id: str) -> threading.Lock:
        """The lock that serialises starting (or replacing) one conversation's runtime."""
        with self._lock:
            return self._start_locks.setdefault(session_id, threading.Lock())

    def _evict_idle(self) -> list[Runtime]:
        """Removes runtimes idle too long from the pool and returns them to be closed (call with the pool lock held)."""
        now = time.monotonic()
        gone = [sid for sid, r in self._runtimes.items() if not r.busy.locked() and now - r.last_used > self.idle_seconds]
        return [self._runtimes.pop(sid) for sid in gone]

    def _evict_one(self) -> Runtime | None:
        """Removes the least recently used idle runtime and returns it to be closed (call with the pool lock held)."""
        idle = [(r.last_used, sid) for sid, r in self._runtimes.items() if not r.busy.locked()]
        if not idle:
            return None
        return self._runtimes.pop(min(idle)[1])

    @staticmethod
    def _open_session(harness: DeepSeekHarness, session_id: str, resume: bool) -> Session:
        """The harness session of a conversation: resumed when it has history; a new one if that history is gone from disk."""
        if resume:
            try:
                return harness.resume_session(session_id)
            except Exception:  # noqa: BLE001  (history pruned or never written)
                log.warning("cannot resume %s; starting it afresh", session_id)
        return harness.start_session(session_id)

    def _start(self, session_id: str, key: tuple, principal: Principal, user: str, user_id: int, llm: dict[str, Any], resume: bool) -> Runtime:
        env = {name: os.environ.get(name, "") for name in FORWARDED}
        env.update({
            "QK3_LLM_BASE_URL": llm["base_url"], "QK3_LLM_MODEL": llm["model"], "QK3_LLM_KEY": llm.get("api_key") or "none",
            "QK3_LLM_CONTEXT": str(int(llm.get("context_window") or 131072)), "QK3_PYTHON": sys.executable, "QK3_BACKEND": str(BACKEND),
            "JWT_SECRET": config.JWT_SECRET, "QDRANT_URL": config.QDRANT_URL, "QDRANT_API_KEY": config.QDRANT_API_KEY,
            "QDRANT_COLLECTION": config.QDRANT_COLLECTION, "APP_ENV": config.APP_ENV, "DATA_DIR": str(config.DATA_DIR),
            "UPLOAD_DIR": str(config.UPLOAD_DIR), "TEMP_DIR": str(config.TEMP_DIR), "DATABASE_URL": config.DATABASE_URL,
            "QK3_SCOPE_TOKEN": identity.issue(principal, config.JWT_SECRET, ttl_seconds=3600, user=user, user_id=user_id, session_id=session_id),
        })
        home, work, user_home = config.DATA_DIR / "dsh", config.DATA_DIR / "dsh-work", config.DATA_DIR / "dsh-home"
        for folder in (home, work, user_home):
            folder.mkdir(parents=True, exist_ok=True)
        # The harness (Node) writes a package cache under $HOME; a service account in a container has no writable home.
        env.update({"HOME": str(user_home), "XDG_CACHE_HOME": str(user_home / ".cache")})
        env.update(self.env)
        harness = DeepSeekHarness(dsh_home=str(home), cwd=str(work), provider="qk3", model=llm["model"], patches=(str(PATCH),), env=env,
                                  reasoning_effort=reasoning_effort(llm), max_tokens=int(llm.get("max_output_tokens") or 4096),
                                  initialize_timeout_seconds=90)
        try:
            harness.start()
            session = self._open_session(harness, session_id, resume or history.exists(session_id))
        except Exception as exc:  # noqa: BLE001  (missing binary, profile error, timeout...)
            harness.close()
            log.exception("agent runtime failed to start for %s", session_id)
            raise AgentUnavailable("Không khởi động được trợ lý AI; báo quản trị viên.") from exc
        return Runtime(session_id, key, harness, session)
