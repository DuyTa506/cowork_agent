"""One-off move of original files from the old upload directory (``UPLOAD_DIR``) into the object store.

Run once when upgrading a deployment that kept originals on a volume:  ``python -m app.storage.migrate [--delete]``.
Safe to repeat: objects already in the store are left alone. With ``--delete`` the local copy is removed once it is stored.
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app import storage
from app.core import config
from app.core.database import SessionLocal
from app.models import Document

log = logging.getLogger(__name__)


def migrate(delete: bool = False) -> dict[str, int]:
    """Copies the originals of every document into the store; returns counts ``{"copied", "already", "missing"}``."""
    store = storage.get_store()
    counts = {"copied": 0, "already": 0, "missing": 0}
    with SessionLocal() as db:
        for stored_name in db.scalars(select(Document.stored_name)):
            key = storage.keys.document(stored_name)
            local = config.UPLOAD_DIR / stored_name
            if store.exists(key):
                counts["already"] += 1
            elif local.is_file():
                store.put_file(key, local)
                counts["copied"] += 1
            else:
                counts["missing"] += 1
                log.warning("no file for %s in the store or in %s", stored_name, config.UPLOAD_DIR)
                continue
            if delete and local.is_file():
                local.unlink()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="remove each local file once it is in the store")
    logging.basicConfig(level=logging.INFO)
    print(migrate(parser.parse_args().delete))


if __name__ == "__main__":
    main()
