"""Checks of a draft's structure that a format check of the rendered file cannot see.

doccheck judges the .docx against Thông tư 68 (fonts, sizes, alignment, lines). What it cannot judge is how the content holds
together: Markdown marks a model left in the text, a passage written twice, a numbering that skips or repeats, an appendix the body
cites but the draft does not have, a "Nơi nhận" without "Như trên". These checks read the draft's data, before rendering.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import tables
from .content import DraftContent, blank, split
from .markup import KHOAN, ROMAN_HEADING

_MARKDOWN = re.compile(r"\*\*|^\s{0,3}#{1,6}\s|`", re.MULTILINE)
_CITES_APPENDIX = re.compile(r"\bphụ\s+lục\b|\b(bảng|danh\s+mục|biểu)\b[^.;:]{0,60}\bkèm\s+theo\b", re.IGNORECASE)
_WORD = re.compile(r"\w+", re.UNICODE)
_ARTICLE = re.compile(r"^Điều\s+\d+")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
MIN_REPEAT = 30  # a repeated passage shorter than this ("Đề nghị:" ...) is not worth a warning
TARGET_OVERLAP = 0.2  # a replacement sharing less of its words with the passage than this looks aimed at another one
NUMBERING_REF = "TT68 Phụ lục I mục II.8"


def _finding(severity: str, message: str, where: str = "", ref: str = "") -> dict[str, str]:
    """A finding in the shape of the format check's (``{"severity", "message", "where", "ref"}``)."""
    return {"severity": severity, "message": message, "where": where[:160], "ref": ref}


def _norm(text: str) -> str:
    """`text` reduced to its words, lower case, for comparing passages."""
    return " ".join(_WORD.findall(unicodedata.normalize("NFC", text).casefold()))


def _roman(text: str) -> int:
    """The value of a roman numeral ("IV" -> 4); unknown letters count as 0."""
    total, prev = 0, 0
    for char in reversed(text):
        value = _ROMAN_VALUES.get(char, 0)
        total = total - value if value < prev else total + value
        prev = max(prev, value)
    return total


def _numbering(blocks: list[dict[str, Any]], where: str) -> list[dict[str, str]]:
    """Checks the numbering of a run of blocks.

    Roman sections must follow each other (I, II, III); the khoản under each section, or under each "Điều", count from 1 without
    gaps or repeats.

    Args:
        blocks: The blocks of the body or of one appendix.
        where: Suffix naming the part in a message (" (Phụ lục II)"), "" for the body.

    Returns:
        Warnings, one per break in the sequence.
    """
    out: list[dict[str, str]] = []
    section, khoan = 0, 0
    for block in blocks:
        if block["kind"] not in ("heading", "para"):
            continue
        text = block["text"].strip()
        if block["kind"] == "heading" and ROMAN_HEADING.match(text):
            number = _roman(text.split(".", 1)[0])
            if number != section + 1:
                out.append(_finding("warning", f"Số mục La Mã không liền mạch{where}: sau mục {section or '(đầu)'} là mục {number}.",
                                    text, NUMBERING_REF))
            section, khoan = number, 0
            continue
        if _ARTICLE.match(text):
            khoan = 0
            continue
        match = KHOAN.match(text)
        if match:
            number = int(match.group(1))
            if number != khoan + 1:
                kind = "lặp số" if number <= khoan else "nhảy số"
                out.append(_finding("warning", f"Số khoản {kind}{where}: sau khoản {khoan or '(đầu)'} là khoản {number}.", text,
                                    NUMBERING_REF))
            khoan = number
    return out


def check(content: DraftContent) -> list[dict[str, str]]:
    """Checks the structure of a draft.

    Args:
        content: The draft.

    Returns:
        Findings ``{"severity", "message", "where", "ref"}``: Markdown left in a field or block (error); a repeated passage; a
        numbering break; an empty appendix; an appendix cited but absent (error) or present but not cited; a table too wide for
        a portrait body; what a table's formulas and sums could not work out; a passage quoting figures a table no longer holds;
        "Kính gửi" without "- Như trên;" in "Nơi nhận".
    """
    out: list[dict[str, str]] = []
    texts = [b["text"] for b in content.blocks if b["kind"] != "table"] + [spec["text"] for spec in content.fields.values()]
    for text in texts:
        if _MARKDOWN.search(text or ""):
            out.append(_finding("error", "Còn ký hiệu Markdown (**, #, `): Word in nguyên các dấu này. In đậm do loại đoạn quyết định.",
                                text))
    seen: dict[str, str] = {}
    for block in content.blocks:
        if block["kind"] == "table":
            continue
        key = _norm(block["text"])
        if len(key) >= MIN_REPEAT and key in seen:
            out.append(_finding("warning", f"Đoạn {block['id']} lặp lại nội dung đoạn {seen[key]}.", block["text"]))
        seen.setdefault(key, block["id"])

    body, appendices = split(content.blocks)
    out += _numbering(body, "")
    for appendix in appendices:
        out += _numbering(appendix.blocks, f" ({appendix.label})")
        if not appendix.blocks:
            out.append(_finding("warning", f"{appendix.label} chưa có nội dung.", appendix.block["text"]))
    citing = next((b["text"] for b in body if b["kind"] != "table" and _CITES_APPENDIX.search(b["text"])), None)
    if citing is not None and not appendices:
        out.append(_finding("error", "Nội dung nhắc tới phụ lục, bảng kèm theo nhưng bản dự thảo chưa có phụ lục: thêm phụ lục "
                                     "(đoạn loại appendix và bảng) hoặc bỏ câu dẫn chiếu.", citing))
    if appendices and citing is None:
        out.append(_finding("warning", "Có phụ lục nhưng nội dung chưa dẫn chiếu tới (ví dụ: '… chi tiết tại Phụ lục kèm theo').",
                            appendices[0].block["text"], "TT68 Phụ lục III Mẫu 15a"))
    for block in body:
        if block["kind"] == "table" and block.get("table") and not tables.fits(block["table"], tables.PORTRAIT_CM):
            out.append(_finding("warning", "Bảng quá rộng cho trang dọc: nên đưa vào phụ lục (tự xoay ngang).",
                                tables.summary(block["table"])))
    for block in content.blocks:
        if block["kind"] == "table" and block.get("table"):
            out += [_finding("warning", f"Bảng {block['id']}: {problem}", block["text"]) for problem in tables.problems(block["table"])]
        if block.get("stale"):
            figures = ", ".join(block["stale"]["figures"])
            out.append(_finding("warning", f"Đoạn {block['id']} nhắc số liệu bảng đã đổi ({figures}): xem lại.", block["text"]))

    to, noi_nhan = content.fields.get("kinh_gui"), content.fields.get("noi_nhan")
    if to and noi_nhan and not blank(to["text"]) and "như trên" not in noi_nhan["text"].casefold():
        out.append(_finding("warning", "Có 'Kính gửi' nhưng 'Nơi nhận' chưa có dòng '- Như trên;'.", noi_nhan["text"],
                            "TT68 Phụ lục I mục II.9"))
    return out


def proposal_checks(content: DraftContent, block_id: str, before: str, after: str) -> list[dict[str, str]]:
    """Checks a text the assistant proposes for one block.

    Args:
        content: The draft, with the proposal recorded.
        block_id: The block the proposal is on.
        before: The block's current text ("" for an insertion).
        after: The proposed text.

    Returns:
        Warnings in the shape of `style_check.compare` (``{"severity", "kind", "message", "where"}``): ``target`` when the proposal
        shares almost no words with the passage it replaces (likely aimed at another one), ``repeat`` when it repeats another
        passage of the draft.
    """
    out: list[dict[str, str]] = []
    new = set(_WORD.findall(after.casefold()))
    if before:
        old = set(_WORD.findall(before.casefold()))
        if old and new and len(old & new) / min(len(old), len(new)) < TARGET_OVERLAP:
            out.append({"severity": "warning", "kind": "target", "message": "Đề xuất gần như thay hết chữ của đoạn: có thể nhắm "
                        "nhầm đoạn, kiểm tra lại đoạn được sửa.", "where": before[:160]})
    key = _norm(after)
    for block in content.blocks:
        if block["id"] != block_id and block["kind"] != "table" and len(key) >= MIN_REPEAT and _norm(block["text"]) == key:
            out.append({"severity": "warning", "kind": "repeat", "message": f"Đề xuất trùng nội dung đoạn {block['id']}.",
                        "where": block["text"][:160]})
            break
    return out
