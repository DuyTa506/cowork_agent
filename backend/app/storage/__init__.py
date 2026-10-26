"""Object storage for the original files (documents in the store, files attached to chats).

`get_store()` returns the process-wide store chosen by configuration: ``OBJECT_STORE=s3`` (MinIO or any S3-compatible server) or
``local`` (a directory, the default for development). Keys are built in `keys`.
"""
from __future__ import annotations

import threading

from app.core import config

from . import keys
from .base import BlobNotFound, BlobStat, BlobStore, ByteStream, guess_content_type
from .local import LocalBlobStore

_store: BlobStore | None = None
_lock = threading.Lock()


def build_store() -> BlobStore:
    """A new store from the process configuration (the bucket is created on first use)."""
    if config.OBJECT_STORE == "s3":
        from .s3 import S3BlobStore

        store = S3BlobStore(config.S3_ENDPOINT, config.S3_ACCESS_KEY, config.S3_SECRET_KEY, config.S3_BUCKET, config.S3_SECURE)
        store.ensure_bucket()
        return store
    return LocalBlobStore(config.OBJECT_DIR)


def get_store() -> BlobStore:
    """The shared store, created on first use."""
    global _store
    with _lock:
        if _store is None:
            _store = build_store()
        return _store


def set_store(store: BlobStore | None) -> None:
    """Replaces the shared store (tests point it at a temporary directory; None forgets it)."""
    global _store
    with _lock:
        _store = store


__all__ = ["BlobNotFound", "BlobStat", "BlobStore", "ByteStream", "LocalBlobStore", "build_store", "get_store", "guess_content_type", "keys",
           "set_store"]
