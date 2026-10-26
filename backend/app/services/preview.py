"""The page view of a document: a PDF that the browser draws itself (pdf.js), so fonts, layout and tables are those of the original.

A PDF is shown as it is. A Word file is turned into a PDF once by LibreOffice (headless) and the result is kept in the object store next
to the original (`<key>.view.pdf`): it is made when the document is processed, or on the first view for documents that came earlier,
and never again. Viewing then costs the server only the bytes of the pages the browser asks for (``Range`` requests).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from app import storage
from app.core import config

log = logging.getLogger(__name__)

VIEW_SUFFIX = ".view.pdf"
TIMEOUT = 120  # seconds LibreOffice may take for one document
WORD_EXTENSIONS = {".doc", ".docx"}
_slots = threading.BoundedSemaphore(2)  # LibreOffice is heavy: at most two conversions at a time in one process


def view_key(key: str) -> str:
    """Where the PDF made from the Word file at `key` is kept."""
    return f"{key}{VIEW_SUFFIX}"


def soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def available() -> bool:
    return soffice() is not None


def _convert(source: Path, target: Path) -> None:
    program = soffice()
    if program is None:
        raise RuntimeError("LibreOffice chưa được cài trên máy này.")
    with tempfile.TemporaryDirectory(dir=config.TEMP_DIR, prefix="qk3-lo-") as work:
        # its own profile folder: two LibreOffice processes sharing one profile block each other
        command = [program, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation=file://{work}/profile",
                   "--convert-to", "pdf", "--outdir", work, str(source)]
        subprocess.run(command, check=True, capture_output=True, timeout=TIMEOUT, cwd=work)
        made = Path(work) / f"{source.stem}.pdf"
        if not made.is_file() or made.stat().st_size == 0:
            raise RuntimeError("LibreOffice không tạo được PDF.")
        shutil.copyfile(made, target)


def build(key: str) -> bool:
    """Makes the PDF of the Word file at `key` unless it exists. Returns whether a view exists afterwards; a failure is logged, not raised."""
    store = storage.get_store()
    target_key = view_key(key)
    if store.exists(target_key):
        return True
    if not available():
        return False
    suffix = Path(key).suffix.lower()
    try:
        with _slots, store.local_copy(key, config.TEMP_DIR) as path, tempfile.TemporaryDirectory(dir=config.TEMP_DIR, prefix="qk3-view-") as out:
            source = Path(out) / f"source{suffix}"  # a plain ASCII name: the converter trips over some file names
            shutil.copyfile(path, source)
            made = Path(out) / "view.pdf"
            _convert(source, made)
            store.put_file(target_key, made, "application/pdf")
        return True
    except Exception as exc:  # noqa: BLE001  (a document that cannot be drawn is still readable as text)
        log.warning("preview: could not build the view of %s: %s", key, exc)
        return False


def key_for(key: str, original_name: str) -> str | None:
    """Key of the PDF to show for the document stored at `key` (building it when a Word file has none yet), or ``None``."""
    suffix = Path(original_name).suffix.lower() or Path(key).suffix.lower()
    if suffix == ".pdf":
        return key
    if suffix in WORD_EXTENSIONS and build(key):
        return view_key(key)
    return None
