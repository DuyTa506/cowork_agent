"""Turns the agent runtime's session events into what the chat screen shows.

The runtime reports each model step once it is complete: the model's reasoning, the tool calls it made (possibly several at once),
the tool results, and finally the answer. The translator folds that stream into *steps* (rows such as "Đã suy nghĩ", "Tìm văn bản")
that are shown as soon as they start and update when they finish, plus the final answer with its sources.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .citations import SourceRegistry, json_values, number_citations

TOOL_PREFIX = "mcp__qk3__"
MODE_LABEL = {"keyword": "từ khóa", "semantic": "ngữ nghĩa", "hybrid": "kết hợp"}
TOOL_TITLE = {
    "search_documents": "Tìm văn bản", "list_documents": "Liệt kê văn bản", "read_document": "Đọc văn bản",
    "search_attachments": "Tìm trong tệp đính kèm", "list_attachments": "Xem tệp đính kèm", "read_attachment": "Đọc tệp đính kèm",
    "summarize_document": "Tóm tắt văn bản", "canvas_create": "Mở canvas", "canvas_read": "Đọc canvas", "canvas_set_fields": "Điền thông tin canvas",
    "canvas_set_content": "Soạn nội dung", "canvas_edit_block": "Đề xuất chỉnh sửa", "canvas_edit_table": "Đề xuất sửa bảng",
    "canvas_check": "Kiểm tra thể thức",
    "canvas_style": "Tra văn phong đơn vị",
}
CANVAS_READS = frozenset({"canvas_read", "canvas_style"})  # canvas tools that leave the draft as it was
GIST_CHARS = 140


@dataclass
class Step:
    """One row of the "what the assistant did" list."""

    id: str
    kind: str  # thinking | tool
    title: str
    summary: str = ""
    status: str = "running"  # running | done | error
    started: int = 0  # ms since epoch
    duration_ms: int = 0
    tool: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON form sent to the client and stored with the message."""
        return {"id": self.id, "kind": self.kind, "title": self.title, "summary": self.summary, "status": self.status,
                "duration_ms": self.duration_ms, "tool": self.tool, "detail": self.detail}


def _gist(text: str) -> str:
    """First sentence of a reasoning text, shortened."""
    line = " ".join(text.split())
    for stop in (". ", "? ", "! "):
        if stop in line:
            line = line.split(stop, 1)[0] + stop.strip()
            break
    return line if len(line) <= GIST_CHARS else line[:GIST_CHARS].rsplit(" ", 1)[0] + "…"


def _args(raw: Any) -> dict[str, Any]:
    """Tool-call arguments (a JSON string or already a dict) as a dict."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


class Translator:
    """Stateful fold over one turn's events.

    `feed(event)` returns the UI events to send now (``{"type": "step", "step": {...}}``, ``{"type": "canvas"}``); after the turn,
    `answer`, `steps`, `registry` and `failure` hold the outcome and `finish()` builds the final text and citations.
    """

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.registry = SourceRegistry()
        self.answer = ""
        self.failure = ""
        self.canvas_changed = False
        self._step_started = 0
        self._calls: dict[str, Step] = {}
        self._call_time: dict[str, int] = {}

    # ----- folding -----
    def feed(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Folds one runtime event; returns the UI events it produces (possibly none)."""
        kind, data, at = event.get("type", ""), event.get("data", {}), int(event.get("time", 0))
        if kind == "step/start":
            self._step_started = at
        elif kind == "assistant/message":
            return self._assistant(data, at)
        elif kind == "tool/call":
            return self._call(data, at)
        elif kind == "tool/result":
            return self._result(data, at)
        elif kind == "turn/end":
            reason = data.get("reason", {})
            if reason.get("kind") not in (None, "completed"):
                self.failure = str(reason.get("message") or reason.get("kind"))
        return []

    def _push(self, step: Step) -> dict[str, Any]:
        """Registers a step and returns its UI event."""
        self.steps.append(step)
        return {"type": "step", "step": step.as_dict()}

    def _assistant(self, data: dict[str, Any], at: int) -> list[dict[str, Any]]:
        message = data.get("message", {})
        blocks = message.get("content", [])
        out: list[dict[str, Any]] = []
        reasoning = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "reasoning").strip()
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        has_calls = any(b.get("type") == "tool-call" for b in blocks)
        if reasoning:
            seconds = max(1, round((at - self._step_started) / 1000)) if self._step_started else 0
            title = f"Đã suy nghĩ {seconds} giây" if seconds else "Đã suy nghĩ"
            out.append(self._push(Step(f"s{len(self.steps) + 1}", "thinking", title, _gist(reasoning), "done", self._step_started,
                                       seconds * 1000, detail={"text": reasoning})))
        if text and not has_calls:
            self.answer = text
        return out

    def _call(self, data: dict[str, Any], at: int) -> list[dict[str, Any]]:
        name = str(data.get("name", ""))
        tool = name.removeprefix(TOOL_PREFIX)
        args = _args(data.get("arguments"))
        step = Step(f"s{len(self.steps) + 1}", "tool", TOOL_TITLE.get(tool, tool), self._call_summary(tool, args), "running", at, tool=tool,
                    detail={"arguments": args})
        self._calls[str(data.get("callId"))], self._call_time[str(data.get("callId"))] = step, at
        return [self._push(step)]

    @staticmethod
    def _call_summary(tool: str, args: dict[str, Any]) -> str:
        """What the call asked for, before its result is known."""
        if tool in ("search_documents", "search_attachments"):
            return f"{MODE_LABEL.get(args.get('mode', 'hybrid'), 'kết hợp')} · “{args.get('query', '')}”"
        if tool in ("read_document", "read_attachment", "summarize_document"):
            return str(args.get("doc_id", ""))
        if tool == "list_documents":
            filters = [str(v) for k, v in args.items() if k != "limit" and v]
            return " · ".join(filters) or "mới nhất"
        return ""

    def _result(self, data: dict[str, Any], at: int) -> list[dict[str, Any]]:
        call_id = str(data.get("message", {}).get("toolCallId", ""))
        step = self._calls.get(call_id)
        if step is None:
            return []
        content = data.get("message", {}).get("content", [])
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        step.duration_ms = max(0, at - self._call_time.get(call_id, at))
        failed = bool(data.get("message", {}).get("isError"))
        results = [] if failed else json_values(text)
        step.status = "error" if failed else "done"
        step.detail["result"] = self._summarise(step.tool, results, failed, text)
        if step.tool in ("search_documents", "search_attachments"):
            n = self.registry.add_results(results)
            docs = {r.get("doc_id") for r in results if isinstance(r, dict)}
            step.summary += f" · {n} đoạn trong {len(docs)} văn bản" if n else " · không có kết quả"
        elif step.tool in ("read_document", "read_attachment") and results and isinstance(results[0], dict) and "doc" in results[0]:
            self.registry.add_document(str(results[0].get("doc_id", "")), str(results[0]["doc"]))
            step.summary = str(results[0]["doc"])[:120]
        elif step.tool == "summarize_document" and results and isinstance(results[0], dict) and "doc" in results[0]:
            self.registry.add_document(str(results[0].get("doc_id", "")), str(results[0]["doc"]))
            step.summary = f"{str(results[0]['doc'])[:100]} · {results[0].get('parts', 1)} phần"
        elif step.tool.startswith("canvas_") and step.tool not in CANVAS_READS:
            self.canvas_changed = self.canvas_changed or not failed
        step.summary += f" · {step.duration_ms / 1000:.1f} giây".replace(".", ",")
        return [{"type": "step", "step": step.as_dict()}]

    @staticmethod
    def _summarise(tool: str, results: list[Any], failed: bool, raw: str) -> dict[str, Any]:
        """The part of a tool result worth showing under its row: the documents it touched, or the error."""
        if failed:
            return {"error": raw[:300]}
        refs, seen = [], set()
        for item in results:
            if isinstance(item, dict) and "doc_id" in item and item["doc_id"] not in seen:
                seen.add(item["doc_id"])
                refs.append({"doc_id": str(item["doc_id"]), "label": str(item.get("doc") or item.get("trich_yeu") or ""),
                             "section": str(item.get("section", ""))})
        return {"documents": refs[:12], "count": len(results)}

    # ----- outcome -----
    def finish(self) -> tuple[str, list[dict[str, Any]]]:
        """The answer with numbered citations and the citation list."""
        return number_citations(self.answer, self.registry)
