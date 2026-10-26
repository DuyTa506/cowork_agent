"""Turns a scanned PDF in the object store into a text companion file next to it."""
from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docx import Document as WordDocument

from app import storage
from app.core import config
from app.parsing import ParsedDocument, ParseError, parse_file
from app.services import settings

from .client import OcrClient, OcrServerError
from . import layout
from .render import RenderError, page_count, pages

log = logging.getLogger(__name__)

class OcrDisabled(RuntimeError):
    """OCR is switched off or not configured."""


class OcrError(RuntimeError):
    """Reading the file failed; the message is meant for the user."""


def companion_key(key: str) -> str:
    """Where the text of the scanned file at `key` is kept."""
    return f"{key}.ocr.docx"


def grounding_key(key: str) -> str:
    """Where the blocks of the scanned file at `key` are kept with their positions on the pages."""
    return f"{key}.ocr.json"


def is_enabled(values: dict[str, Any]) -> bool:
    return bool(values.get("enabled") and values.get("base_url") and values.get("model"))


def ensure_companion(key: str, values: dict[str, Any], on_progress: Callable[[int, int], None] | None = None) -> str:
    """Reads the scanned PDF at `key` with OCR unless its companion already exists; returns the companion's key.

    Raises:
        OcrDisabled: OCR is off or has no server configured.
        OcrError: the PDF cannot be rendered, the server failed, or nothing could be read.
        storage.BlobNotFound: the original is gone.
    """
    store = storage.get_store()
    target_key = companion_key(key)
    if store.exists(target_key):
        return target_key
    if not is_enabled(values):
        raise OcrDisabled("OCR chưa được bật (Quản trị → Hệ thống → OCR).")
    limit = int(values.get("max_pages") or 60)
    client = OcrClient(values)
    texts: list[str] = []
    pages_read: list[dict[str, Any]] = []
    try:
        with store.local_copy(key, config.TEMP_DIR) as path, tempfile.TemporaryDirectory(dir=config.TEMP_DIR, prefix="qk3-ocr-") as tmp:
            try:
                total = min(page_count(path), limit)
                for number, png in enumerate(pages(path, limit), start=1):
                    text, blocks = client.read_page(png)
                    texts.append(text)
                    pages_read.append({"page": number, "text": text, "blocks": [b.as_dict() for b in blocks]})
                    if on_progress:
                        on_progress(number, total)
            except RenderError as exc:
                raise OcrError(str(exc)) from exc
            except OcrServerError as exc:
                raise OcrError(str(exc)) from exc
            if not any(t.strip() for t in texts):
                raise OcrError("OCR không đọc được chữ nào từ tệp này.")
            out = Path(tmp) / "text.docx"
            layout.write_docx(list(zip(texts, [p["blocks"] or None for p in pages_read])), out)
            store.put_file(target_key, out, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            if any(p["blocks"] for p in pages_read):  # boxes are on a 0-1000 scale of the page, whatever size it was rendered at
                where = Path(tmp) / "blocks.json"
                where.write_text(json.dumps({"scale": 1000, "pages": pages_read}, ensure_ascii=False), encoding="utf-8")
                store.put_file(grounding_key(key), where, "application/json")
    finally:
        client.close()
    log.info("ocr: %s pages read from %s", len(texts), key)
    return target_key



def parse_with_ocr(key: str, on_progress: Callable[[int, int], None] | None = None) -> ParsedDocument:
    """Parses the stored file at `key`; a PDF without a text layer is read with OCR first when the administrator switched that on.

    Raises:
        ParseError: unreadable file, or a scan while OCR is off.
        OcrError: OCR is on but could not read the file.
        storage.BlobNotFound: the original is gone.
    """
    store = storage.get_store()
    try:
        with store.local_copy(key, config.TEMP_DIR) as path:
            return parse_file(path)
    except ParseError as exc:
        values = settings.cache.get("ocr")
        # no text layer, or a PDF whose text layer the extractor chokes on (a few odd fonts/layouts): the page images are still readable
        unreadable_text = "lớp chữ" in str(exc) or (key.lower().endswith(".pdf") and "Không đọc được tệp" in str(exc))
        if not unreadable_text or not is_enabled(values):
            raise
    text_key = ensure_companion(key, values, on_progress)
    with store.local_copy(text_key, config.TEMP_DIR) as path:
        parsed = parse_file(path)
    parsed.ocr = True
    return parsed
