"""TCVN3/ABC ('.VnTime', '.VnArial'...) -> Unicode, for runs typed in the legacy Vietnamese fonts still found in old .doc files.

The table is the one in doccheck's crates/dc-spell/src/enc.rs (codes 0xA1..0xFE); VNI is not handled (none in the corpus).
"""
from __future__ import annotations

_TCVN3 = {
    0xA1: 'Ă', 0xA2: 'Â', 0xA3: 'Ê', 0xA4: 'Ô', 0xA5: 'Ơ', 0xA6: 'Ư', 0xA7: 'Đ', 0xA8: 'ă', 0xA9: 'â',
    0xAA: 'ê', 0xAB: 'ô', 0xAC: 'ơ', 0xAD: 'ư', 0xAE: 'đ', 0xB5: 'à', 0xB6: 'ả', 0xB7: 'ã', 0xB8: 'á',
    0xB9: 'ạ', 0xBB: 'ằ', 0xBC: 'ẳ', 0xBD: 'ẵ', 0xBE: 'ắ', 0xC6: 'ặ', 0xC7: 'ầ', 0xC8: 'ẩ', 0xC9: 'ẫ',
    0xCA: 'ấ', 0xCB: 'ậ', 0xCC: 'è', 0xCE: 'ẻ', 0xCF: 'ẽ', 0xD0: 'é', 0xD1: 'ẹ', 0xD2: 'ề', 0xD3: 'ể',
    0xD4: 'ễ', 0xD5: 'ế', 0xD6: 'ệ', 0xD7: 'ì', 0xD8: 'ỉ', 0xDC: 'ĩ', 0xDD: 'í', 0xDE: 'ị', 0xDF: 'ò',
    0xE1: 'ỏ', 0xE2: 'õ', 0xE3: 'ó', 0xE4: 'ọ', 0xE5: 'ồ', 0xE6: 'ổ', 0xE7: 'ỗ', 0xE8: 'ố', 0xE9: 'ộ',
    0xEA: 'ờ', 0xEB: 'ở', 0xEC: 'ỡ', 0xED: 'ớ', 0xEE: 'ợ', 0xEF: 'ù', 0xF1: 'ủ', 0xF2: 'ũ', 0xF3: 'ú',
    0xF4: 'ụ', 0xF5: 'ừ', 0xF6: 'ử', 0xF7: 'ữ', 0xF8: 'ứ', 0xF9: 'ự', 0xFA: 'ỳ', 0xFB: 'ỷ', 0xFC: 'ỹ',
    0xFD: 'ý', 0xFE: 'ỵ',
}
_TABLE = {chr(k): v for k, v in _TCVN3.items()}

def legacy_font(name: str | None) -> str | None:
    """'tcvn3' | 'tcvn3_upper' for a '.Vn*' font ('.VnTimeH' draws its lower-case codes as capitals), else None."""
    first = (name or "").split(";")[0].strip()
    if len(first) > 3 and first.startswith(".Vn"):
        return "tcvn3_upper" if first.endswith("H") and len(first) > 4 else "tcvn3"
    return None

def tcvn3_to_unicode(text: str, upper: bool = False) -> str:
    """Converts word by word; a word that already has a character outside Latin-1 is Unicode and stays as it is."""
    out = []
    for word in text.split(" "):
        if any(ord(c) > 0xFF for c in word):
            out.append(word)
            continue
        conv = "".join(_TABLE.get(c, c) for c in word)
        out.append(conv.upper() if upper else conv)
    return " ".join(out)
