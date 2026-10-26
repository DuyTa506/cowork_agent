"""Plain text for the page from what a person or a model typed, and the numbering conventions of a document's body.

A Word document cannot print Markdown: "**1.**" would come out with its asterisks. Emphasis in a draft follows from the kind of the
block, as Thông tư 68 assigns it to each numbering level, so the marks are removed wherever text enters a draft.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_HASH = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)
_BULLET = re.compile(r"^[•*–—·][ \t]*")
_MARKER = re.compile(r"^(?:[-+][ \t]*|[a-zđ]\)[ \t]+|\d{1,2}\)[ \t]+)")
ROMAN_HEADING = re.compile(r"^[IVXLC]{1,6}\.\s+\S")
KHOAN = re.compile(r"^(\d{1,2})\.\s+\S")
KHOAN_TITLE_WORDS = 8  # a numbered line this short, without a closing full stop, is the title of a khoản


def clean(text: str) -> str:
    """Removes Markdown emphasis, heading marks and code ticks.

    Args:
        text: Text as typed; None counts as empty.

    Returns:
        The text with ``**bold**`` reduced to ``bold``, stray ``**`` and backticks dropped, and leading ``#`` marks removed.
    """
    out = _BOLD.sub(r"\1", text or "").replace("**", "").replace("`", "")
    return _HASH.sub("", out)


def item_text(text: str) -> str:
    """Gives a list line its mark.

    Args:
        text: The line as typed.

    Returns:
        The line opening with "- ", unless it already opens with "-", "+", "a)" or "1)"; a bullet such as "•" becomes "-".
    """
    line = _BULLET.sub("- ", text.strip(), count=1)
    if _MARKER.match(line):
        return re.sub(r"^([-+])[ \t]*", r"\1 ", line)
    return f"- {line}"


def _upper_ratio(text: str) -> float:
    """Share of the letters of `text` that are upper case (0 when it has no letter)."""
    letters = [c for c in text if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def is_khoan_title(text: str) -> bool:
    """Tells the title of a khoản from a numbered sentence.

    Args:
        text: One block of the body.

    Returns:
        True for "1. Thời gian, địa điểm" or "2. Linh kiện, vật tư kỹ thuật:" (printed bold), False for
        "1. Các cơ quan rà soát ... ." (only its number is bold).
    """
    line = text.strip()
    match = KHOAN.match(line)
    if not match or "\n" in line or line.endswith((".", ";", ",")):
        return False
    return len(line[match.end(1) + 1:].split()) <= KHOAN_TITLE_WORDS


def kind_for(kind: str, text: str) -> str:
    """The kind a body block should have for its text.

    Thông tư 68 prints a roman section heading ("I. MỤC ĐÍCH") and the title of a khoản ("1. Thời gian") bold on their own line,
    the number of a khoản without a title bold, and points and dashes regular.

    Args:
        kind: The kind the block was written as (``heading``, ``para``, ``item``, ...).
        text: Its text.

    Returns:
        ``heading`` for a roman heading or a khoản title written as a paragraph; ``para`` for a numbered sentence written as a
        heading; ``item`` for a "a)", "-" or "+" line written as a heading; otherwise `kind` unchanged.
    """
    line = text.strip()
    if kind == "para" and ROMAN_HEADING.match(line) and _upper_ratio(line) >= 0.8:
        return "heading"
    if kind == "heading" and _MARKER.match(line):
        return "item"
    if kind in ("para", "heading") and KHOAN.match(line):
        return "heading" if is_khoan_title(line) else "para"
    return kind
