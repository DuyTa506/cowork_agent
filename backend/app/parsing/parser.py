from __future__ import annotations
import re
from pathlib import Path

from .header import detect_classification, extract_footer, extract_header, find_footer
from .models import Metadata, ParsedDocument, Section
from .reader import ReadError, load_model, to_lines
from .structure import build_sections

ParseError = ReadError
_LEGAL_BASIS = re.compile(r"^(Căn cứ|Theo đề nghị)\b", re.IGNORECASE)

def parse_file(path: str | Path) -> ParsedDocument:
    """Reads a .doc/.docx/.pdf administrative document into metadata, a numbered-section tree and its footer."""
    model, fmt, warnings = load_model(path)
    lines = to_lines(model)
    meta = Metadata()
    body_start = extract_header(lines, meta)
    meta.classification = detect_classification(lines)
    footer_start, footer_end = find_footer(lines, body_start)
    footer = extract_footer(lines[footer_start:footer_end], meta)
    root = build_sections(lines, body_start, footer_start)
    if footer_end < len(lines):  # phụ lục / biểu mẫu after the signature
        annex = build_sections(lines, footer_end, len(lines))
        if annex.blocks:  # lines before the first "Phụ lục" marker, e.g. a table title
            first = annex.blocks[0]
            root.children.append(Section("annex", "", first.text[:120], first.pi, annex.blocks[1:], []))
        root.children += annex.children
    meta.legal_bases = [b.text for b in root.blocks if _LEGAL_BASIS.match(b.text)][:40]

    if not meta.title:
        meta.title = next((l.text for l in lines if not l.empty and len(l.text) <= 200), "")
    if not any(not l.empty for l in lines):
        warnings.append("Không trích xuất được chữ (có thể là tệp ảnh/scan).")
    else:
        if not meta.doc_type:
            warnings.append("Không nhận diện được loại văn bản.")
        if not meta.date_text:
            warnings.append("Không tìm thấy dòng địa danh, ngày tháng.")
        if footer_start == len(lines):
            warnings.append("Không tìm thấy khối 'Nơi nhận'/chữ ký.")
    return ParsedDocument(path=str(path), format=fmt, metadata=meta, root=root, footer=footer, warnings=warnings)
