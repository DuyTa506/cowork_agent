"""Rewrites the Word text file of every scanned document from the blocks the OCR model gave (`<key>.ocr.json`), without reading the pages
again: use it after the layout rules (app/ocr/layout.py) changed. Documents are then queued to be processed again so their metadata,
index and tags follow the new text.

    python tools/rebuild_ocr_companions.py [--no-requeue]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select  # noqa: E402

from app import ocr, storage  # noqa: E402
from app.core import config  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Document, DocumentState  # noqa: E402
from app.ocr import layout  # noqa: E402
from app.services import jobs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-requeue", action="store_true")
    requeue = not ap.parse_args().no_requeue
    store = storage.get_store()
    done = skipped = 0
    with SessionLocal() as db:
        for document in db.scalars(select(Document).order_by(Document.id)):
            key = storage.keys.document(document.stored_name)
            where = ocr.grounding_key(key)
            if not store.exists(where):
                continue
            with store.local_copy(where, config.TEMP_DIR) as path:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            pages = [(p.get("text", ""), p["blocks"] or None) for p in data["pages"]]
            if any(not blocks and not text for text, blocks in pages):
                skipped += 1  # a page whose text was not kept: needs a new OCR run
                continue
            with tempfile.TemporaryDirectory(dir=config.TEMP_DIR) as tmp:
                out = Path(tmp) / "text.docx"
                layout.write_docx(pages, out)
                store.put_file(ocr.companion_key(key), out, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            if requeue:
                document.state = DocumentState.UPLOADED
                jobs.enqueue(db, document.id)
            done += 1
        db.commit()
    print(f"viết lại {done} tệp, bỏ qua {skipped} (thiếu chữ của trang, cần OCR lại)")


if __name__ == "__main__":
    main()
