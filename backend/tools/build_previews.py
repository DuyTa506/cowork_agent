"""Draws the page view (PDF) of every Word document that has none yet, so nobody waits for it on first view.

    python tools/build_previews.py [--workers 4]
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select  # noqa: E402

from app import storage  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Document  # noqa: E402
from app.services import preview  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    workers = ap.parse_args().workers
    if not preview.available():
        sys.exit("Chưa cài LibreOffice (soffice) nên chưa dựng được bản xem của tệp Word.")
    with SessionLocal() as db:
        keys = [storage.keys.document(d.stored_name) for d in db.scalars(select(Document)) if d.stored_name.lower().endswith(tuple(preview.WORD_EXTENSIONS))]
    store = storage.get_store()
    todo = [k for k in keys if not store.exists(preview.view_key(k))]
    print(f"{len(keys)} tệp Word, {len(todo)} chưa có bản xem", flush=True)
    done = failed = 0
    with ThreadPoolExecutor(workers) as pool:
        for n, ok in enumerate(pool.map(preview.build, todo), 1):
            done += ok
            failed += not ok
            if n % 50 == 0:
                print(f"{n}/{len(todo)}  xong {done}  lỗi {failed}", flush=True)
    print(f"xong: {done} bản xem, {failed} lỗi")


if __name__ == "__main__":
    main()
