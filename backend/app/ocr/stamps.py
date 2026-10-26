"""Reads the seal, signature and date stamps that a PDF carries as pictures, so number, date and signer are not lost.

The text layer of a PDF that was signed and stamped afterwards stops at the typed text: "Số: /QĐ-BTM" and "ngày ... tháng ..." stay
blank and the signer's name is missing, because the numbers and the stamp are pictures laid over the page. A document with a seal and
a signature always has a number and an issue date, so these pages are read by OCR and only the empty fields are filled.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app import storage
from app.core import config
from app.parsing import ParsedDocument
from app.services import settings
from app.parsing.header import fill_from_images

from .client import OcrClient, OcrServerError
from .render import RenderError, page_png, stamp_pages
from .service import is_enabled

log = logging.getLogger(__name__)


def missing(parsed: ParsedDocument) -> list[str]:
    """The fields a stamped document must have and the text layer did not give."""
    meta = parsed.metadata
    return [name for name, value in (("số", meta.number), ("ngày", meta.date), ("người ký", meta.signer_name)) if not value]


def read_stamps(key: str, parsed: ParsedDocument, values: dict[str, Any] | None = None) -> list[str]:
    """`read_stamps_file` for the stored file at `key`."""
    if parsed.format != "pdf" or parsed.ocr:
        return []
    store = storage.get_store()
    with store.local_copy(key, config.TEMP_DIR) as path:
        return read_stamps_file(path, parsed, values)


def read_stamps_file(path: Path, parsed: ParsedDocument, values: dict[str, Any] | None = None) -> list[str]:
    """Fills the missing number, date and signer of a stamped PDF from the pages that carry the stamps; returns the fields that were found.

    Marks `parsed.metadata.stamped`. Does nothing for other formats, for a scan (already read by OCR), or when OCR is off; a failing
    OCR server leaves the document as it was (the fields stay empty and the review reason says so)."""
    if parsed.format != "pdf" or parsed.ocr:
        return []
    pages = stamp_pages(path)
    parsed.metadata.stamped = bool(pages)
    if not pages or not missing(parsed):
        return []
    values = values if values is not None else settings.cache.get("ocr")  # read only when a PDF has something to look at
    if not is_enabled(values):
        return []
    texts: dict[int, list[str]] = {}
    client = OcrClient(values)
    try:
        for index in pages:
            text, _ = client.read_page(page_png(path, index))
            texts[index] = [re.sub(r"[*#|_`]+", "", t).strip() for t in text.splitlines()]  # markdown the model adds around bold lines
    except (OcrServerError, RenderError) as exc:
        log.warning("ocr: stamps of %s not read: %s", path.name, exc)
        return []
    finally:
        client.close()
    first = texts.get(0, [])  # the header with the stamped number and date
    rest = [line for index in sorted(texts) if index != 0 for line in texts[index]]  # the signature block, wherever the text ends
    found = fill_from_images(parsed.metadata, first, rest)
    if found:
        parsed.warnings.append("Đã đọc " + ", ".join(dict.fromkeys(found)) + " từ ảnh con dấu/chữ ký bằng OCR.")
    return found
