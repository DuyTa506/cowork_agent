"""Puts every .doc/.docx/.pdf of a folder tree into the document store, the way an upload does, then the worker indexes them.

The unit of a file comes from its folder (sample corpus: "Bộ Tham mưu/Phòng Công binh/..."); a file under a "văn bản mật" folder is
declared secret. Files already in the store (same content in the same unit) are skipped, so the command can be repeated after an
interruption or when new files appear. Runs against whatever DATABASE_URL / OBJECT_STORE / S3_* the environment names.

    python tools/import_corpus.py "/path/Du lieu" [--limit N] [--user admin] [--under "Bộ Tham mưu/Ban CNTT"]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select  # noqa: E402

from app import storage  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Document, DocumentState, User  # noqa: E402
from app.org import place  # noqa: E402
from app.services import jobs, organization  # noqa: E402

EXTENSIONS = (".doc", ".docx", ".pdf")
SKIP_DIRS = {"phan_loai_pdf"}  # copies of the PDFs, sorted by text quality
MAGIC = (b"\xd0\xcf\x11\xe0", b"PK\x03\x04", b"%PDF")


def find_files(root: Path) -> list[Path]:
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found += [Path(folder) / f for f in sorted(files) if f.lower().endswith(EXTENSIONS) and not f.startswith("~$")]
    return found


def digest_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--user", default="admin", help="account the documents are recorded as uploaded by")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--under", default="", help='folder path the files belong under when `root` itself is not in the unit tree, e.g. "Bộ Tham mưu/Ban CNTT"')
    a = ap.parse_args()
    root = Path(a.root)
    tree = organization.tree()
    store = storage.get_store()
    files = find_files(root)[: a.limit or None]
    added = skipped = bad = 0
    with SessionLocal() as db:
        uploader = db.scalar(select(User).where(User.username == a.user))
        if uploader is None:
            sys.exit(f"Không có tài khoản '{a.user}'. Khởi động API một lần để tạo quản trị viên, hoặc dùng --user.")
        known = {(d.sha256, d.unit_id) for d in db.execute(select(Document.sha256, Document.unit_id)).all()}
        for number, path in enumerate(files, 1):
            parts = [p for p in a.under.split("/") if p] + list(path.relative_to(root).parts[:-1])
            placed = place(tree, parts)
            unit = placed.unit_id
            try:
                with open(path, "rb") as fh:
                    head = fh.read(4)
                if not head.startswith(MAGIC) or path.stat().st_size == 0:
                    bad += 1
                    continue
                digest = digest_of(path)
                if (digest, unit) in known:
                    skipped += 1
                    continue
                stored = f"{uuid.uuid4().hex}{path.suffix.lower()}"
                store.put_file(storage.keys.document(stored), path, storage.guess_content_type(stored))
                document = Document(original_name=path.name[:255], stored_name=stored, file_size=path.stat().st_size, sha256=digest, unit_id=unit,
                                    level=placed.level, state=DocumentState.UPLOADED, uploaded_by_id=uploader.id,
                                    extra={"declared_secret": placed.level == "mat", "source_folder": "/".join(parts)}, title=path.stem)
                db.add(document)
                db.flush()
                jobs.enqueue(db, document.id)
                known.add((digest, unit))
                added += 1
            except Exception as exc:  # noqa: BLE001  (one unreadable file must not stop the rest)
                db.rollback()
                bad += 1
                print(f"  bỏ qua {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            if added % 100 == 0:
                db.commit()
                print(f"{number}/{len(files)}  thêm {added}  bỏ qua {skipped}  lỗi {bad}", flush=True)
        db.commit()
    print(f"xong: {len(files)} tệp, thêm {added}, đã có {skipped}, lỗi {bad}")


if __name__ == "__main__":
    main()
