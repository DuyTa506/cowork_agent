"""Object-storage interface: where the original files of documents and chat attachments live.

The application never touches a document's file by path. It asks a `BlobStore` for the object under a key, so the same code runs
against a plain directory (development, tests) and against any S3-compatible server (MinIO in the deployment).
"""
from __future__ import annotations

import mimetypes
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

CHUNK_SIZE = 1 << 18


class BlobNotFound(FileNotFoundError):
    """No object under the key."""


class ByteStream(Protocol):
    """A byte source read in fixed-size blocks (never line by line: the data is binary)."""

    def __iter__(self) -> Iterator[bytes]: ...

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class BlobStat:
    """What is known about an object without reading it."""

    size: int
    content_type: str
    etag: str | None = None


def guess_content_type(name: str) -> str:
    """Media type from a file name (``application/octet-stream`` when unknown)."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class BlobStore(ABC):
    """Keyed objects. Keys are ``/``-separated paths without leading slash, e.g. ``documents/<id>.docx``."""

    @abstractmethod
    def put_file(self, key: str, path: Path, content_type: str = "") -> None:
        """Stores the file at `path` under `key`, replacing any object there."""

    @abstractmethod
    def put(self, key: str, data: BinaryIO, size: int, content_type: str = "") -> None:
        """Stores `size` bytes read from `data` under `key`."""

    @abstractmethod
    def stat(self, key: str) -> BlobStat:
        """Size and type of an object. Raises `BlobNotFound`."""

    @abstractmethod
    def open(self, key: str, offset: int = 0, length: int | None = None) -> ByteStream:
        """Reads an object (or `length` bytes from `offset`, for HTTP range requests). The caller closes the stream; exhausting it closes it.
        Raises `BlobNotFound`."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Removes an object; a missing one is not an error."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Removes every object whose key starts with `prefix` (non-empty); returns how many were removed."""

    def exists(self, key: str) -> bool:
        """Whether an object is stored under `key`."""
        try:
            self.stat(key)
        except BlobNotFound:
            return False
        return True

    def download(self, key: str, target: Path) -> Path:
        """Copies an object to the local file `target` (parent directories are created) and returns it."""
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = self.open(key)
        try:
            with open(target, "wb") as out:
                for block in stream:
                    out.write(block)
        finally:
            stream.close()
        return target

    @contextmanager
    def local_copy(self, key: str, scratch: Path | None = None) -> Iterator[Path]:
        """A local file with the object's bytes (same extension as the key, which parsers go by), removed on exit."""
        if scratch is not None:
            scratch.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="blob-", dir=scratch))
        try:
            yield self.download(key, folder / Path(key).name)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
