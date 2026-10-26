"""Spelling check on top of doccheck, in the form the "Kiểm tra chính tả" screen needs.

A Word file or a PDF is checked with the whole doccheck pipeline (the same one "Kiểm tra thể thức" runs) and then reduced to its
spelling findings, the way doccheck's own "Chính tả" screen does. Pasted text and .txt / .md files go through `doccheck.spell_text`,
line by line. doccheck's display helpers (`doccheck.ui.*`) are not a documented API, so everything that depends on them is here.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path
from typing import Any

import doccheck
from doccheck import errmsg
from doccheck.ui import analysis, spelltext

from app.core.errors import ValidationFailed
from app.services.formatcheck import engine as format_engine

MAX_CHARS = spelltext.MAX_CHARS
TEXT_EXTENSIONS = spelltext.TEXT_EXTS
MARKDOWN_EXTENSIONS = spelltext.MARKDOWN_EXTS
KIND_LABEL = {"word": "Word", "pdf": "PDF", "text": "Văn bản"}
PDF_NOTE = "PDF không sửa trực tiếp được: sửa ở tệp gốc rồi xuất lại PDF."
NO_FINDINGS = "Không thấy lỗi chính tả nào."


# ----- what is a spelling row -----
def is_spelling_note(manual: dict[str, Any]) -> bool:
    """A hand-fix note about spelling (doccheck names them ``M:spl:...`` / ``SPELL.*``)."""
    return str(manual.get("id", "")).startswith("M:spl:") or str(manual.get("rule", "")).startswith("SPELL")


def _note_place(manual: dict[str, Any]) -> tuple[int, int, int] | None:
    """``(pi, start, end)`` a spelling note stands for (its id ends with them)."""
    match = re.search(r":(\d+):(\d+):(\d+)$", str(manual.get("id", "")))
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def normalize_word(word: str) -> str:
    return unicodedata.normalize("NFC", word).strip().lower()


def _counts(items: list, manual: list) -> dict[str, int]:
    return {"format": 0, "spelling": len(items) + len(manual), "items": len(items), "manual": len(manual)}


# ----- building the payload -----
def only_spelling(payload: dict[str, Any]) -> dict[str, Any]:
    """The check payload of a Word file / PDF without its format findings (items, notes, banner and paragraph flags)."""
    out = dict(payload)
    out["items"] = [item for item in payload["items"] if item["kind"] == "spelling"]
    out["manual"] = [m for m in payload["manual"] if is_spelling_note(m)]
    out["banner"] = []
    out["paras"] = [{**para, "msgs": []} for para in payload["paras"]]
    out["counts"] = _counts(out["items"], out["manual"])
    return out


def analyze_file(source: Path, kind: str, profile: str, name: str, session_id: str) -> dict[str, Any]:
    """Spelling findings of a Word file or a text-layer PDF."""
    outcome = format_engine.analyze(source, kind, profile, True, name, session_id)
    payload = only_spelling(outcome.payload)
    payload["kind"], payload["kind_label"] = kind, KIND_LABEL[kind]
    payload["can_fix"] = kind == "word"
    payload["note"] = PDF_NOTE if kind == "pdf" else ""
    payload["chars"] = sum(len(p["text"]) for p in payload["paras"])
    return payload


def decode_text(raw: bytes) -> tuple[str, str, str]:
    """``(text, encoding to write back, note)`` of a text file's bytes.

    Raises:
        ValidationFailed: not a plain text file.
    """
    try:
        text, encoding, note = spelltext.decode(raw)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    if encoding == "latin-1":  # no Unicode at all: a legacy Vietnamese code page; keep going as Windows-1258 and say so
        text, encoding, note = raw.decode("cp1258", errors="replace"), "utf-8", "Tệp không phải Unicode: đọc theo bảng mã Windows-1258 và lưu lại bằng UTF-8."
    return text, encoding, note


def analyze_text(text: str, name: str, markdown: bool, encoding: str = "utf-8", eol: str = "\n", note: str = "") -> dict[str, Any]:
    """Spelling findings of a text (lines separated by ``\\n``).

    Raises:
        ValidationFailed: empty or longer than `MAX_CHARS`.
    """
    if not text.strip():
        raise ValidationFailed(spelltext.EMPTY_MSG)
    if len(text) > MAX_CHARS:
        raise ValidationFailed(spelltext.too_long(len(text)))
    try:
        issues = doccheck.spell_text(text, source="typed", lm="auto", tone_style="majority", markdown=markdown, **format_engine.deep_options())
    except Exception as exc:  # noqa: BLE001  (doccheck raises plain exceptions with Vietnamese messages)
        raise ValidationFailed(errmsg.vi_error(exc, "")) from exc
    payload = spelltext.build(text, issues)
    lines = text.split("\n")
    for item in payload["items"]:  # doccheck's Word items carry the wrong word as `found`; the text ones only its visible form
        item["found"] = _slice(lines[item["pi"]], item["start"], item["end"])
    payload.update(facts={"doc_type": None, "origin": None}, banner=[], est_pages=False, tiers=analysis.TIER_VI, kind="text",
                   kind_label=KIND_LABEL["text"], can_fix=True, note=note, chars=len(text), markdown=markdown,
                   file={"enc": encoding, "eol": eol})
    return payload


# ----- ignore list -----
def apply_ignore(payload: dict[str, Any], words: list[str]) -> dict[str, Any]:
    """The payload without the findings whose word is on the ignore list (compared in lower case); ``ignored`` says how many."""
    wanted = {normalize_word(w) for w in words if w.strip()}
    if not wanted:
        return {**payload, "ignored": 0}
    out = copy.copy(payload)
    dropped: set[tuple[int, int, int]] = set()
    kept_items = []
    for item in payload["items"]:
        if normalize_word(item.get("found") or item.get("before") or "") in wanted:
            dropped.add((item["pi"], item["start"], item["end"]))
        else:
            kept_items.append(item)
    kept_manual = []
    for note in payload["manual"]:
        place = _note_place(note)
        if is_spelling_note(note) and normalize_word(note.get("found", "")) in wanted:
            if place:
                dropped.add(place)
        else:
            kept_manual.append(note)
    out["items"], out["manual"] = kept_items, kept_manual
    out["paras"] = [{**p, "marks": [m for m in p["marks"] if (p["pi"], m[0], m[1]) not in dropped]} for p in payload["paras"]]
    out["counts"] = {**payload["counts"], **_counts(kept_items, kept_manual)}
    out["ignored"] = len(payload["items"]) + len(payload["manual"]) - len(kept_items) - len(kept_manual)
    return out


# ----- corrections -----
def _slice(line: str, start: int, end: int) -> str:
    """The UTF-16 range [start, end) of `line`."""
    return line.encode("utf-16-le")[2 * start:2 * end].decode("utf-16-le")


def _cut(line: str, start: int, end: int, replacement: str) -> str:
    """`line` with the UTF-16 range [start, end) replaced (the offsets the screen and `spelltext` use)."""
    data = line.encode("utf-16-le")
    return (data[:2 * start] + replacement.encode("utf-16-le") + data[2 * end:]).decode("utf-16-le")


def correct_text(text: str, items: list[dict[str, Any]], ids: list[str]) -> tuple[str, list[str], list[dict[str, str]]]:
    """`text` (lines separated by ``\\n``) with the edits `ids` written in. Returns ``(text, applied ids, failed)``."""
    by_id = {item["id"]: item for item in items}
    lines = text.split("\n")
    applied, failed = [], []
    chosen: dict[int, list[dict[str, Any]]] = {}
    for item_id in dict.fromkeys(ids):
        item = by_id.get(item_id)
        if item is None or not (0 <= item["pi"] < len(lines)):
            failed.append({"id": item_id, "reason": "Mục này không còn trong văn bản."})
            continue
        chosen.setdefault(item["pi"], []).append(item)
    for pi, edits in chosen.items():
        last = None
        for item in sorted(edits, key=lambda e: e["start"], reverse=True):  # from the end, so earlier offsets stay valid
            if last is not None and item["end"] > last:
                failed.append({"id": item["id"], "reason": "Chồng lên một chỗ sửa khác."})
                continue
            lines[pi] = _cut(lines[pi], item["start"], item["end"], item["raw_after"])
            last = item["start"]
            applied.append(item["id"])
    return "\n".join(lines), applied, failed


def apply_word(source: Path, profile: str, ids: list[str], mode: str, out: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Writes `out` (.docx) with only the edits `ids` (as Word tracked changes unless `mode` is ``apply``)."""
    return format_engine.apply(source, profile, True, ids, mode, out)


def recount_word(path: Path, profile: str, name: str, session_id: str) -> dict[str, int]:
    """Spelling counts of a corrected copy, so the screen can show how much is left."""
    payload = only_spelling(format_engine.analyze(path, "word", profile, True, name, session_id).payload)
    return payload["counts"]


# ----- report -----
def report_text(name: str, payload: dict[str, Any]) -> str:
    """Plain-text list of the spelling findings (the ones still shown, after the ignore list)."""
    paras = {p["pi"]: p for p in payload["paras"]}
    unit = "Dòng" if payload.get("kind") == "text" else "Đoạn"
    lines = [f"Tệp: {name}", f"Kết quả soát chính tả: {payload['counts']['spelling']} mục", ""]
    rows = [("item", i) for i in payload["items"]] + [("note", m) for m in payload["manual"] if is_spelling_note(m)]
    rows.sort(key=lambda r: ((r[1].get("pi") if r[0] == "item" else (r[1].get("pis") or [0])[0]) or 0, r[1].get("start", 0)))
    for number, (kind, row) in enumerate(rows, 1):
        pi = row["pi"] if kind == "item" else (row.get("pis") or [0])[0]
        place = f"{unit} {pi + 1}"
        page = paras.get(pi, {}).get("page") or paras.get(pi, {}).get("pg")
        if page:
            place = f"Trang {page}, {unit.lower()} {pi + 1}"
        if kind == "item":
            lines.append(f"{number}. [{row['label']}] {place}: “{row['found']}” → “{row['raw_after']}”")
            lines.append(f"   …{row['ctx'][0]}{row['found']}{row['ctx'][1]}…")
        else:
            lines.append(f"{number}. [Cần tự xem lại] {place}: “{row.get('found', '')}”" + (f" → gợi ý “{row['suggestion']}”" if row.get("suggestion") else ""))
        lines.append(f"   {row['explain'] if kind == 'item' else row.get('message', '')}")
    if not rows:
        lines.append(NO_FINDINGS)
    return "\n".join(lines) + "\n"
