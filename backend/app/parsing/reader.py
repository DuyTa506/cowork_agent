from __future__ import annotations
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import doccheck
from doccheck import DocModel

from .legacy import legacy_font, tcvn3_to_unicode

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")
SUPPORTED = {".doc", ".docx", ".pdf"}

class ReadError(Exception):
    """The file cannot be read; the message is meant for the user."""

@dataclass
class Line:
    pi: int
    text: str
    align: str = "left"
    bold: bool = False
    italic: bool = False
    where: str = "body"
    table: int | None = None
    row: int | None = None
    col: int | None = None
    ind_left_cm: float = 0.0
    empty: bool = False

def _magic(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head.startswith(_OLE):
        return "ole"
    if head.startswith(b"PK"):
        return "zip"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    return "unknown"

def _is_encrypted_ole(path: Path) -> bool:
    return _ENCRYPTED_PACKAGE in path.read_bytes()

def load_model(path: str | Path) -> tuple[DocModel, str, list[str]]:
    """Reads a .doc/.docx/.pdf into doccheck's DocModel, trusting the file's magic bytes over its extension."""
    src = Path(path)
    if not src.is_file():
        raise ReadError("Không tìm thấy tệp.")
    ext = src.suffix.lower()
    if ext not in SUPPORTED:
        raise ReadError(f"Định dạng {ext or '(không có đuôi)'} chưa được hỗ trợ.")
    kind = _magic(src)
    warnings: list[str] = []
    if kind == "ole" and ext == ".docx" and _is_encrypted_ole(src):
        raise ReadError("Tệp Word đã đặt mật khẩu nên không đọc được.")
    if kind == "rtf":
        raise ReadError("Tệp RTF cần LibreOffice để đọc; hãy lưu lại dưới dạng DOCX.")
    want = {"ole": ".doc", "zip": ".docx", "pdf": ".pdf"}.get(kind, ext)
    tmp = None
    target = src
    if want != ext:
        warnings.append(f"Đuôi tệp {ext} không khớp nội dung ({want}); đã đọc theo nội dung.")
        tmp = tempfile.TemporaryDirectory(prefix="qk3-parse-")
        target = Path(tmp.name) / ("f" + want)
        os.symlink(src.resolve(), target)
    try:
        model = doccheck.load(str(target))
    except Exception as exc:  # doccheck raises plain OSError/ValueError with the path in the message
        msg = str(exc).replace(str(target), src.name)
        if kind == "ole" and want == ".doc" and "password" in msg.lower():
            raise ReadError("Tệp Word đã đặt mật khẩu nên không đọc được.") from exc
        raise ReadError(f"Không đọc được tệp: {msg}") from exc
    finally:
        if tmp is not None:
            tmp.cleanup()
    return model, want.lstrip("."), warnings

def _para_text(p, default_font: str | None) -> str:
    """Paragraph text with the runs typed in a legacy (TCVN3) font converted to Unicode."""
    text = p.text
    kinds = [(r, legacy_font(r.font or default_font)) for r in p.runs]
    if not any(k for _, k in kinds):
        text_out = text
    else:
        out: list[str] = []
        cur = 0
        for r, kind in sorted(kinds, key=lambda x: x[0].start):
            if r.start < cur:
                continue
            out.append(text[cur:r.start])
            seg = text[r.start:r.end]
            out.append(tcvn3_to_unicode(seg, kind == "tcvn3_upper") if kind else seg)
            cur = r.end
        out.append(text[cur:])
        text_out = "".join(out)
    label = p.label
    return (label + " " if label and not label.endswith(" ") else label) + text_out

def to_lines(model: DocModel) -> list[Line]:
    """Body paragraphs in document order (page headers/footers are repeated furniture, not content)."""
    from .textutil import norm
    lines: list[Line] = []
    for p in model.body():
        text = norm(_para_text(p, model.default_font))
        runs = [r for r in p.runs if r.text.strip()]
        lines.append(Line(
            pi=p.pi, text=text, align=p.align,
            bold=bool(runs) and all(r.bold for r in runs),
            italic=bool(runs) and all(r.italic for r in runs),
            where=p.where, table=p.table, row=p.row, col=p.col,
            ind_left_cm=p.ind_left_cm, empty=not text,
        ))
    return lines
