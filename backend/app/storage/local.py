"""`BlobStore` on a directory: for development and tests, and for sites without an object-storage server."""
from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from .base import CHUNK_SIZE, BlobNotFound, BlobStat, BlobStore, guess_content_type


class _FileStream:
    """Reads a byte window of a file in blocks."""

    def __init__(self, path: Path, offset: int, length: int | None):
        self._file = open(path, "rb")
        self._file.seek(offset)
        self._left = length

    def read(self, size: int = -1) -> bytes:
        if self._left is not None:
            size = self._left if size < 0 else min(size, self._left)
        data = self._file.read(size)
        if self._left is not None:
            self._left -= len(data)
        return data

    def __iter__(self) -> Iterator[bytes]:
        try:
            while block := self.read(CHUNK_SIZE):
                yield block
        finally:
            self.close()

    def close(self) -> None:
        self._file.close()


class LocalBlobStore(BlobStore):
    """Objects are files under `root`; a key is a relative path. Writes are atomic (temporary file, then rename)."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not key or self.root not in path.parents:
            raise ValueError(f"invalid object key: {key!r}")
        return path

    def put_file(self, key: str, path: Path, content_type: str = "") -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        shutil.copyfile(path, partial)
        os.replace(partial, target)

    def put(self, key: str, data: BinaryIO, size: int, content_type: str = "") -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        with open(partial, "wb") as out:
            shutil.copyfileobj(data, out, CHUNK_SIZE)
        os.replace(partial, target)

    def stat(self, key: str) -> BlobStat:
        path = self._path(key)
        if not path.is_file():
            raise BlobNotFound(key)
        info = path.stat()
        return BlobStat(info.st_size, guess_content_type(path.name), f"{info.st_mtime_ns:x}-{info.st_size:x}")

    def open(self, key: str, offset: int = 0, length: int | None = None) -> _FileStream:
        path = self._path(key)
        if not path.is_file():
            raise BlobNotFound(key)
        return _FileStream(path, offset, length)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        if not prefix:
            raise ValueError("a non-empty prefix is required")
        removed = 0
        for path in list(self.root.rglob("*")):
            if path.is_file() and path.relative_to(self.root).as_posix().startswith(prefix):
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    @contextmanager
    def local_copy(self, key: str, scratch: Path | None = None) -> Iterator[Path]:
        """The object is already a local file: use it in place instead of copying."""
        path = self._path(key)
        if not path.is_file():
            raise BlobNotFound(key)
        yield path
