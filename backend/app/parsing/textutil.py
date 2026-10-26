from __future__ import annotations
import re
import unicodedata

_WS = re.compile(r"[ \t  -​ 　﻿]+")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

def norm(text: str) -> str:
    """NFC, no control characters, collapsed whitespace: the form every regex here expects."""
    text = unicodedata.normalize("NFC", _CTRL.sub(" ", text or ""))
    return _WS.sub(" ", text).strip()

def fold(text: str) -> str:
    """Upper-case without diacritics ('Cộng hoà' -> 'CONG HOA') so spelling and tone-placement variants match."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").upper()

def is_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)
