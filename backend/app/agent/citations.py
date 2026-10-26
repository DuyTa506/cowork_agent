"""Sources and citation numbering.

The agent cites passages with the ``cite`` code the search tools return (``12#3``: chunk 3 of document 12) written in square
brackets. Models mistype or invent codes, so only codes that a tool actually returned in this turn are honoured; the rest are
removed. Honoured codes are renumbered ``[1]``, ``[2]`` in order of first use, one number per (document, section).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_BRACKET = re.compile(r"\[([^\[\]\n]{1,200})\]")
_CODE = re.compile(r"(?:att)?\d+#\d+")


def json_values(text: str) -> list[Any]:
    """Every JSON value in `text`, which may hold several concatenated (the way MCP tools return a list of results)."""
    decoder, index, out = json.JSONDecoder(), 0, []
    while index < len(text):
        while index < len(text) and text[index] in " \r\n\t,":
            index += 1
        if index >= len(text):
            break
        try:
            value, index = decoder.raw_decode(text, index)
        except ValueError:
            break
        out.extend(value if isinstance(value, list) else [value])
    return out


@dataclass
class Source:
    """A passage the agent saw in this turn."""

    cite: str
    doc_id: str
    doc: str = ""
    section: str = ""
    text: str = ""
    pi: tuple[int, int] = (-1, -1)


@dataclass
class SourceRegistry:
    """The passages tools returned during one turn, by cite code."""

    sources: dict[str, Source] = field(default_factory=dict)

    def add_results(self, results: list[Any]) -> int:
        """Records the search hits among `results` (dicts with a ``cite``); returns how many were added."""
        added = 0
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("cite"), str) and "doc_id" in item:
                pi = item.get("pi") or [-1, -1]
                self.sources[item["cite"]] = Source(item["cite"], str(item["doc_id"]), str(item.get("doc", "")), str(item.get("section", "")),
                                                    str(item.get("text", "")), (int(pi[0]), int(pi[1])))
                added += 1
        return added

    def add_document(self, doc_id: str, doc: str) -> None:
        """Records a whole-document source (read or summarised in full), citeable as ``<id>#0``."""
        self.sources.setdefault(f"{doc_id}#0", Source(f"{doc_id}#0", doc_id, doc))


def number_citations(answer: str, registry: SourceRegistry) -> tuple[str, list[dict[str, Any]]]:
    """Rewrites the cite codes of `answer` as ``[1]`` ``[2]`` and returns ``(text, citations)``.

    A bracket may hold several codes (``[12#0, 12#3]``); it becomes ``[1][2]``. Unknown codes disappear. Each citation is
    ``{"n", "cite", "doc_id", "doc", "section", "text", "pi": [first, last]}``; sources of the same document and section share a
    number.
    """
    numbers: dict[tuple[str, str], int] = {}
    citations: list[dict[str, Any]] = []

    def number_of(source: Source) -> int:
        key = (source.doc_id, source.section)
        if key not in numbers:
            numbers[key] = len(numbers) + 1
            citations.append({"n": numbers[key], "cite": source.cite, "doc_id": source.doc_id, "doc": source.doc, "section": source.section,
                              "text": source.text, "pi": list(source.pi)})
        return numbers[key]

    def replace(match: re.Match[str]) -> str:
        codes = _CODE.findall(match.group(1))
        if not codes or _CODE.sub("", match.group(1)).strip(" ,;"):
            return match.group(0)  # an ordinary bracket, not a citation
        found = [registry.sources[c] for c in codes if c in registry.sources]
        marks = sorted({number_of(s) for s in found})
        return "".join(f"[{n}]" for n in marks)

    return _BRACKET.sub(replace, answer), citations
