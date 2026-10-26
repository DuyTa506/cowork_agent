"""Summaries of whole documents, for the `summarize_document` tool.

Reading a long document page by page through the agent loop fills the model's context and costs a round trip per page. Here the
summary is produced server-side: one call when the document fits the model's window, otherwise map-reduce (summarise each
group of sections, then summarise the summaries). The result is a short text the agent can show or build on.
"""
from __future__ import annotations

from typing import Any

from .llm import LlmClient

SYSTEM = (
    "Bạn là cán bộ văn thư của Quân khu 3, tóm tắt văn bản hành chính quân sự. Viết bằng tiếng Việt, văn phong hành chính nghiêm "
    "túc, ngắn gọn, đủ ý. Giữ nguyên chính xác số liệu, thời gian, địa điểm, tên đơn vị, người chịu trách nhiệm, thời hạn. Chỉ dùng "
    "thông tin có trong văn bản, không suy diễn, không thêm ý kiến."
)
SINGLE_PROMPT = (
    "Tóm tắt văn bản dưới đây theo cấu trúc: (1) Mục đích, yêu cầu; (2) Nội dung chính; (3) Thời gian, địa điểm, lực lượng; "
    "(4) Trách nhiệm, thời hạn. Bỏ mục không có thông tin.{focus}\n\n=== VĂN BẢN ===\n{body}"
)
MAP_PROMPT = (
    "Đây là một phần của văn bản dài ({part}/{parts}). Tóm tắt phần này, giữ nguyên số liệu, thời gian, tên đơn vị, trách nhiệm, thời "
    "hạn; không bỏ ý quan trọng.{focus}\n\n=== PHẦN ===\n{body}"
)
REDUCE_PROMPT = (
    "Dưới đây là tóm tắt từng phần của một văn bản. Hợp nhất thành một bản tóm tắt thống nhất theo cấu trúc: (1) Mục đích, yêu cầu; "
    "(2) Nội dung chính; (3) Thời gian, địa điểm, lực lượng; (4) Trách nhiệm, thời hạn. Không lặp ý; bỏ mục không có thông tin.{focus}"
    "\n\n=== CÁC PHẦN ===\n{body}"
)
MAX_SINGLE_PASS_CHARS = 150_000
MAX_REDUCE_ROUNDS = 3


def single_pass_budget(context_window: int) -> int:
    """Largest document (in characters) summarised in one call: roughly half the model's window, capped."""
    return max(8_000, min(MAX_SINGLE_PASS_CHARS, int(context_window * 1.2)))


def render(chunks: list[dict[str, Any]]) -> str:
    """The document text in reading order with its section headings (the metadata chunk first)."""
    lines: list[str] = []
    last_path: tuple[str, ...] = ()
    for chunk in chunks:
        path = tuple(chunk.get("path") or ())
        if path and path != last_path and chunk.get("part") != "meta":
            lines.append(" > ".join(path))
        last_path = path
        lines.append(chunk["text"])
    return "\n".join(lines)


def _groups(chunks: list[dict[str, Any]], budget: int) -> list[str]:
    """Splits the document into consecutive groups of at most `budget` characters, preferring to cut where a top-level section
    starts, so each group is a coherent run of sections."""
    groups: list[list[dict[str, Any]]] = [[]]
    size, top = 0, None
    for chunk in chunks:
        head = (chunk.get("path") or [None])[0]
        length = len(chunk["text"])
        if groups[-1] and (size + length > budget or (head != top and size > budget * 0.6)):
            groups.append([])
            size = 0
        groups[-1].append(chunk)
        size, top = size + length, head
    return [render(g) for g in groups if g]


class Summarizer:
    """Summarises a document's chunks with the configured model.

    Args:
        llm: Client for the chat model.
        context_window: The model's window in tokens (decides single pass vs map-reduce).
    """

    def __init__(self, llm: LlmClient, context_window: int = 131072):
        self.llm, self.budget = llm, single_pass_budget(context_window)

    def summarize(self, chunks: list[dict[str, Any]], focus: str = "") -> dict[str, Any]:
        """Returns ``{"summary", "method": "single"|"map_reduce", "parts", "chars"}``."""
        extra = f"\nLưu ý trọng tâm theo yêu cầu của người dùng: {focus.strip()}" if focus.strip() else ""
        body = render(chunks)
        if len(body) <= self.budget:
            return {"summary": self.llm.complete(SYSTEM, SINGLE_PROMPT.format(body=body, focus=extra)), "method": "single", "parts": 1,
                    "chars": len(body)}
        parts = _groups(chunks, self.budget)
        partial = [self.llm.complete(SYSTEM, MAP_PROMPT.format(part=i, parts=len(parts), body=part, focus=extra))
                   for i, part in enumerate(parts, 1)]
        for _ in range(MAX_REDUCE_ROUNDS):
            joined = "\n\n".join(f"[Phần {i}]\n{text}" for i, text in enumerate(partial, 1))
            if len(joined) <= self.budget:
                break
            half = (len(partial) + 1) // 2  # too long to merge at once: merge in two halves first
            partial = [self.llm.complete(SYSTEM, REDUCE_PROMPT.format(body="\n\n".join(partial[:half]), focus=extra)),
                       self.llm.complete(SYSTEM, REDUCE_PROMPT.format(body="\n\n".join(partial[half:]), focus=extra))]
        joined = "\n\n".join(f"[Phần {i}]\n{text}" for i, text in enumerate(partial, 1))
        return {"summary": self.llm.complete(SYSTEM, REDUCE_PROMPT.format(body=joined, focus=extra)), "method": "map_reduce",
                "parts": len(parts), "chars": len(body)}
