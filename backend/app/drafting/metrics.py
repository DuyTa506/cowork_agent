"""Printed width of Times New Roman text, measured without the font installed on the server.

The renderer uses these widths to size the header columns, the lines under names and titles, and the columns of tables.
`tnr_widths.json` holds the advance width of each character in em, regular and bold, measured on Tinos (a font with the metrics of
Times New Roman). Kerning is ignored: it shortens a header line by less than 1 %.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

WIDTHS_FILE = Path(__file__).with_name("tnr_widths.json")
CM_PER_PT = 2.54 / 72


@lru_cache(maxsize=1)
def _widths() -> dict[str, dict[str, float]]:
    """Loads the width table once.

    Returns:
        ``{"regular": {char: em}, "bold": {char: em}}``.
    """
    data = json.loads(WIDTHS_FILE.read_text(encoding="utf-8"))
    return {"regular": data["regular"], "bold": data["bold"]}


def width_cm(text: str, size_pt: float, *, bold: bool = False) -> float:
    """Measures `text` set on one line.

    Args:
        text: The text; it is NFC-normalised so composed and decomposed Vietnamese letters measure the same.
        size_pt: Font size in points.
        bold: Whether the text is bold.

    Returns:
        The width in cm. A character missing from the table counts as wide as "n".
    """
    table = _widths()["bold" if bold else "regular"]
    fallback = table["n"]
    return sum(table.get(ch, fallback) for ch in unicodedata.normalize("NFC", text)) * size_pt * CM_PER_PT


def wrap(text: str, size_pt: float, room_cm: float, *, bold: bool = False) -> list[str]:
    """Breaks `text` into the lines Word would print in a column, at word boundaries.

    Args:
        text: The text to break.
        size_pt: Font size in points.
        room_cm: Width of the column in cm.
        bold: Whether the text is bold.

    Returns:
        The lines, in order; ``[""]`` for an empty text. A word wider than the column stays whole on its own line.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and width_cm(candidate, size_pt, bold=bold) > room_cm:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]
