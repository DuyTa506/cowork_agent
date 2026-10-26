"""A scanned document as the page images it came from, with the blocks the OCR model found on them (position, kind, text).

The viewer draws the blocks over the page, and a cited passage lights up the blocks that hold it: each block carries `pi`, the range of
paragraph indexes of the Word text file (what citations point at) that were written from it.
"""
from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from typing import Any

from app import ocr, storage
from app.core import config
from app.core.errors import NotFound
from app.ocr import layout, render

_PDFIUM = threading.Lock()  # pdfium is not thread-safe: the browser asks for several pages at once, each in its own request thread
PAGE_EDGE = 1600  # pixels on the longest side of a page image shown in the browser


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _data(key: str) -> dict[str, Any] | None:
    store = storage.get_store()
    where = ocr.grounding_key(key)
    if not store.exists(where):
        return None
    with store.local_copy(where, config.TEMP_DIR) as path:
        return json.loads(Path(path).read_text(encoding="utf-8"))


def blocks(key: str, paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
    """``{"pages": n, "blocks": [{page, label, box, text, pi}]}`` for the scan at `key`; `paragraphs` are the viewer paragraphs of its
    Word text file. Raises `NotFound` when the file was not read with block positions."""
    data = _data(key)
    if data is None:
        raise NotFound("Văn bản này chưa có dữ liệu vị trí khối chữ.")
    wanted = [(p["pi"], _norm(p["text"])) for p in paragraphs if p["text"].strip()]
    at = 0
    out: list[dict[str, Any]] = []
    for page in data["pages"]:
        page_blocks = page["blocks"]
        found: dict[int, list[int]] = {}
        for src, text in layout.flat_texts(layout.page_items(page.get("text", ""), page_blocks)):
            if src is None:
                continue
            target = _norm(text)
            for ahead in range(at, min(at + 60, len(wanted))):
                if wanted[ahead][1] == target:
                    found.setdefault(src, []).append(wanted[ahead][0])
                    at = ahead + 1
                    break
        for n, block in enumerate(page_blocks):
            pis = found.get(n)
            out.append({"page": page["page"], "label": block["label"], "box": block["box"], "text": block["text"],
                        "pi": [min(pis), max(pis)] if pis else None})
    return {"pages": len(data["pages"]), "blocks": out}


def page_png(key: str, number: int) -> bytes:
    """PNG of page `number` (1-based) of the original PDF at `key`."""
    import pypdfium2 as pdfium

    with storage.get_store().local_copy(key, config.TEMP_DIR) as path, _PDFIUM:
        try:
            pdf = pdfium.PdfDocument(str(path))
        except Exception as exc:  # noqa: BLE001
            raise render.RenderError(f"Không mở được PDF: {exc}") from exc
        try:
            if not 1 <= number <= len(pdf):
                raise NotFound("Không có trang này.")
            page = pdf[number - 1]
            try:
                width, height = page.get_size()
                image = page.render(scale=PAGE_EDGE / max(width, height)).to_pil().convert("RGB")
            finally:
                page.close()
        finally:
            pdf.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()
