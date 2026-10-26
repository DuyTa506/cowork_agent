from __future__ import annotations
import re

from .models import Block, Section
from .reader import Line

_ROMAN = r"(?:XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)"
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("annex", re.compile(r"^((?:PHỤ LỤC|Phụ lục)\b[^.;:]{0,60})$")),
    ("phan", re.compile(r"^(Phần\s+(?:thứ\s+\S+|[IVXLC]+|\d+)|PHẦN\s+\S+)", re.UNICODE)),
    ("chuong", re.compile(r"^(Chương\s+(?:[IVXLC]+|\d+))\b", re.IGNORECASE)),
    ("muc", re.compile(r"^(Mục\s+(?:\d+|[IVXLC]+))\b", re.IGNORECASE)),
    ("dieu", re.compile(r"^(Điều\s+\d+)\b", re.IGNORECASE)),
    ("roman", re.compile(rf"^({_ROMAN})\s*[.)]\s+\S")),
    ("upper", re.compile(r"^([A-H])\.\s+[A-ZÀ-Ỹ]{2}")),
    ("decimal", re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+(?=[A-ZÀ-Ỹ])")),
    ("cau", re.compile(r"^(Câu\s+\d+)\b", re.IGNORECASE)),
    ("number", re.compile(r"^(\d{1,2})(?:\.\s+|\)\s*)\S")),
    ("letter", re.compile(r"^([a-zđ])\)\s*\S")),
]
_RANK = {"root": 0, "annex": 1, "phan": 1, "chuong": 2, "muc": 3, "dieu": 4, "roman": 5, "upper": 5, "number": 6, "cau": 6, "decimal": 7, "letter": 10}
_BULLET = re.compile(r"^[-–—+•*]\s+")

def classify(text: str) -> tuple[str, str, int] | None:
    """(kind, marker, rank) when the line opens a numbered unit (Điều, I., 1., 1.1., a)), else None."""
    for kind, rx in _PATTERNS:
        m = rx.match(text)
        if m:
            marker = m.group(1)
            rank = _RANK[kind]
            if kind == "decimal":
                rank = min(7 + marker.count(".") - 1, 9)
            return kind, marker, rank
    return None

def _table_blocks(lines: list[Line], start: int, end: int) -> dict[int, list[int]]:
    """Table index -> line indexes, for the tables that lie entirely in [start, end) and are not 1x1 layout wrappers."""
    by_table: dict[int, list[int]] = {}
    for i, l in enumerate(lines):
        if l.table is not None:
            by_table.setdefault(l.table, []).append(i)
    keep: dict[int, list[int]] = {}
    for t, idxs in by_table.items():
        if min(idxs) < start or max(idxs) >= end:
            continue
        cells = {(lines[i].row, lines[i].col) for i in idxs}
        if len(cells) < 2:
            continue
        keep[t] = idxs
    return keep

def _render_table(lines: list[Line], idxs: list[int]) -> str:
    grid: dict[tuple[int, int], list[str]] = {}
    for i in idxs:
        l = lines[i]
        if l.text:
            grid.setdefault((l.row or 0, l.col or 0), []).append(l.text)
    rows = sorted({r for r, _ in grid})
    out = []
    for r in rows:
        cols = sorted(c for rr, c in grid if rr == r)
        out.append(" | ".join(" ".join(grid[(r, c)]) for c in cols))
    return "\n".join(out)

def build_sections(lines: list[Line], start: int, end: int) -> Section:
    root = Section("root")
    stack: list[tuple[int, Section]] = [(0, root)]
    tables = _table_blocks(lines, start, end)
    emitted: set[int] = set()
    for i in range(start, end):
        l = lines[i]
        if l.empty:
            continue
        if l.table in tables:
            if l.table not in emitted:
                emitted.add(l.table)
                text = _render_table(lines, tables[l.table])
                if text:
                    stack[-1][1].blocks.append(Block("table", text, l.pi))
            continue
        cls = classify(l.text)
        if cls:
            kind, marker, rank = cls
            while stack[-1][0] >= rank:
                stack.pop()
            sec = Section(kind, marker, l.text, l.pi)
            stack[-1][1].children.append(sec)
            stack.append((rank, sec))
        elif _BULLET.match(l.text):
            stack[-1][1].blocks.append(Block("list_item", l.text, l.pi))
        else:
            stack[-1][1].blocks.append(Block("para", l.text, l.pi))
    return root
