"""PDF pages as PNG images for the OCR model."""
from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

LONGEST_EDGE = 2048  # the model was trained on pages scaled to at most this many pixels on the longest side


class RenderError(Exception):
    """The PDF could not be opened or drawn."""


def _open(path: Path):
    """Opens the PDF with its form fields drawn: a visible digital signature or a filled field (the stamped number, day and month of a
    signed document) is an annotation whose picture is not part of the page content and stays blank otherwise."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    pdf.init_forms()  # before the first page is loaded; does nothing when the file has no form
    return pdf


def page_count(path: Path) -> int:
    try:
        pdf = _open(path)
    except Exception as exc:  # noqa: BLE001  (pdfium raises PdfiumError for corrupt or encrypted files)
        raise RenderError(f"Không mở được PDF: {exc}") from exc
    try:
        return len(pdf)
    finally:
        pdf.close()


def pages(path: Path, limit: int) -> Iterator[bytes]:
    """PNG bytes of the first `limit` pages, one at a time (a long file is never held in memory as images)."""
    try:
        pdf = _open(path)
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"Không mở được PDF: {exc}") from exc
    try:
        for index in range(min(len(pdf), limit)):
            page = pdf[index]
            try:
                width, height = page.get_size()  # points
                scale = LONGEST_EDGE / max(width, height)
                image = page.render(scale=scale, may_draw_forms=True).to_pil().convert("RGB")
            finally:
                page.close()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            yield buffer.getvalue()
    finally:
        pdf.close()


_STAMP_ANNOTS = {3, 13, 15, 20}  # FPDF_ANNOT_ FREETEXT, STAMP, INK, WIDGET (form field, visible signature)


def _has_stamp_annotation(page) -> bool:
    import pypdfium2.raw as raw

    for i in range(raw.FPDFPage_GetAnnotCount(page.raw)):
        annot = raw.FPDFPage_GetAnnot(page.raw, i)
        try:
            if raw.FPDFAnnot_GetSubtype(annot) in _STAMP_ANNOTS:
                return True
        finally:
            raw.FPDFPage_CloseAnnot(annot)
    return False


STAMP_PAGE_LIMIT = 4  # the first page and up to three others: the signature sits on the page where the text ends, before the annexes


def stamp_pages(path: Path) -> list[int]:
    """Indexes of the pages (the first, then others in order) that carry a seal, a signature or a number/date stamp the text layer does
    not hold: a picture that is not the whole page, or a form field / visible digital signature (annotations).

    A picture covering a page is a scan and is the OCR's job as a whole; nothing of the kind means nothing is hidden from the text layer."""
    try:
        pdf = _open(path)
    except Exception:  # noqa: BLE001
        return []
    found: list[int] = []
    try:
        for index in range(len(pdf)):
            if len(found) >= STAMP_PAGE_LIMIT:
                break
            page = pdf[index]
            try:
                width, height = page.get_size()
                stamped = _has_stamp_annotation(page)
                for obj in page.get_objects():
                    if obj.type != 3:  # FPDF_PAGEOBJ_IMAGE
                        continue
                    left, bottom, right, top = obj.get_bounds()
                    w, h = (right - left) / width, (top - bottom) / height
                    if w > 0.9 and h > 0.9:
                        return []  # a scan with a text layer: no stamps to look for
                    if w > 0.01 and h > 0.005:
                        stamped = True
                if stamped:
                    found.append(index)
            finally:
                page.close()
    finally:
        pdf.close()
    return found


def page_png(path: Path, index: int) -> bytes:
    """One page as PNG bytes, the way `pages` draws it."""
    try:
        pdf = _open(path)
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"Không mở được PDF: {exc}") from exc
    try:
        page = pdf[index]
        try:
            width, height = page.get_size()
            image = page.render(scale=LONGEST_EDGE / max(width, height), may_draw_forms=True).to_pil().convert("RGB")
        finally:
            page.close()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()
