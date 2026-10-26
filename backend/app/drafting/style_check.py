"""Deterministic checks on a draft's wording. No model is called.

`compare` flags facts a replacement adds (a warning: the figure was not in the passage) or drops (a note). `wording` flags the words
and stock phrases in `style_rules.yaml`. `sections` notes a heading that most of the unit's documents of this kind have and the
draft does not. None of these block a change; the person accepts or rejects it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.org import UnitTree
from app.org.units import key as fold_key

from . import style, tables

_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b|\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b", re.IGNORECASE)
_SYMBOL = re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐ][\w./\-]*|\b\d{1,4}/[A-ZĐ]{1,8}(?:-[A-ZĐ0-9]{1,10})+\b")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*/\s*\d+(?:[.,]\d+)?\b|\b\d+(?:[.,]\d+)?\s*%|\b\d{2,}\b")
_COMRADE = re.compile(r"(?i)(?<!\w)đồng chí\s+([^,.;:\n]{1,80})")
_OUTLINE = re.compile(r"^(.+?) \((\d+)% văn bản\)")
_HEADING = re.compile(r"^(?:[IVXLCDM]{1,6}|điều\s+\d+)\s*[.:\-–]\s*", re.IGNORECASE)
_ROLE = frozenset("trưởng phó chủ nhiệm phòng ban cục bộ chỉ huy tư lệnh tham mưu chính trị hậu cần kỹ thuật "
                  "các đồng chí thủ trưởng".split())
# a unit name shorter than this (folded) matches too much ("Ban", "Cục")
_MIN_UNIT = 10
SECTION_SHARE = 60


@dataclass(frozen=True)
class Fact:
    """One piece of information taken from a passage, compared as a set."""

    kind: str
    value: str


@lru_cache(maxsize=1)
def _tree() -> UnitTree:
    return UnitTree.load()


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(start, end):
            chars[index] = " "
    return "".join(chars)


def _names(text: str) -> set[str]:
    """Personal names after 'đồng chí', not a title ('đồng chí Trưởng phòng' is not a name)."""
    found: set[str] = set()
    for match in _COMRADE.finditer(text):
        name: list[str] = []
        for word in match.group(1).split():
            bare = word.strip(".,;")
            if not bare[:1].isupper():
                break
            if fold_key(bare).lower() in _ROLE:
                if name:
                    break
                continue
            name.append(bare)
        if len(name) >= 2:
            found.add(" ".join(name))
    return found


def _units(text: str, tree: UnitTree) -> set[str]:
    """Names of units of the organisation that the passage mentions, in their usual spelling."""
    haystack = f" {fold_key(text)} "
    found: set[str] = set()
    for unit in tree.units.values():
        for raw in (unit.name, *unit.aliases):
            name = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
            folded = fold_key(name)
            if len(folded) < _MIN_UNIT or " " not in folded:
                continue
            if f" {folded} " in haystack:
                found.add(name)
                break
    return found


def facts(text: str, tree: UnitTree | None = None) -> set[Fact]:
    """Numbers and ratios, dates, document symbols, unit names and personal names in `text`."""
    tree = _tree() if tree is None else tree
    found: set[Fact] = set()
    spans: list[tuple[int, int]] = []
    for pattern, kind in ((_SYMBOL, "symbol"), (_DATE, "date")):
        for match in pattern.finditer(text):
            found.add(Fact(kind, re.sub(r"\s+", " ", match.group(0))))
            spans.append(match.span())
    rest = _mask(text, spans)
    for match in _NUMBER.finditer(rest):
        found.add(Fact("number", re.sub(r"\s+", "", match.group(0))))
    found.update(Fact("unit", name) for name in _units(text, tree))
    found.update(Fact("name", name) for name in _names(text))
    return found


def compare(before: str, after: str, tree: UnitTree | None = None) -> list[dict[str, str]]:
    """Facts in `after` that `before` does not have (warnings) and facts it drops (notes).

    A number that still appears inside a date or symbol that remains is not reported as dropped."""
    tree = _tree() if tree is None else tree
    old, new = facts(before, tree), facts(after, tree)
    kept = {fact.value for fact in new}
    findings: list[dict[str, str]] = []
    for fact in sorted(new - old, key=lambda item: (item.kind, item.value)):
        findings.append({"severity": "warning", "kind": "added", "message": f"Có thêm '{fact.value}' không có trong đoạn gốc.",
                         "where": fact.value})
    for fact in sorted(old - new, key=lambda item: (item.kind, item.value)):
        if any(fact.value in value for value in kept):
            continue
        findings.append({"severity": "info", "kind": "dropped", "message": f"Bỏ '{fact.value}'.", "where": fact.value})
    return findings


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)", text.casefold()) is not None


def wording(text: str) -> list[dict[str, str]]:
    """Words the rules file says not to use, and stock phrases that say nothing."""
    data = style._rules()
    findings: list[dict[str, str]] = []
    for word in data["words"]:
        avoid = word.get("avoid")
        if avoid and _contains(text, avoid):
            findings.append({"severity": "warning", "kind": "word", "message": f"Dùng '{word['use']}' thay cho '{avoid}'.", "where": avoid})
    for phrase in data.get("avoid_phrases", []):
        if _contains(text, phrase):
            findings.append({"severity": "info", "kind": "phrase", "message": f"Cụm '{phrase}' nên viết cụ thể hơn.", "where": phrase})
    return findings


def _heading(text: str) -> str:
    return _HEADING.sub("", text).strip().casefold()


def sections(content: Any, guide: dict[str, Any]) -> list[dict[str, str]]:
    """Headings that at least 60% of the unit's documents of this kind have, and this draft does not. Notes only."""
    present = {_heading(block["text"]) for block in content.blocks if block["kind"] == "heading" and block["text"].strip()}
    kind = content.template.name.casefold()
    findings: list[dict[str, str]] = []
    for line in guide.get("outline", []):
        match = _OUTLINE.match(line)
        if not match or int(match.group(2)) < SECTION_SHARE:
            continue
        heading, key = match.group(1), _heading(match.group(1))
        if any(key == got or (len(key) >= 8 and (key in got or got in key)) for got in present):
            continue
        findings.append({"severity": "info", "kind": "section",
                         "message": f"{match.group(2)}% {kind} của đơn vị có mục {heading}.", "where": heading})
    return findings


def blanks(content: Any) -> int:
    """How many '…' placeholders are left for a person to fill in (a table counts its cells holding one)."""
    texts = [field["text"] for field in content.fields.values()] + [b["text"] for b in content.blocks if b["kind"] != "table"]
    return sum(text.count("…") for text in texts) + sum(tables.blanks(b["table"]) for b in content.blocks if b.get("table"))
