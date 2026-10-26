"""`BlobStore` on an S3-compatible server (MinIO in the deployment), through the `minio` client."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from minio import Minio
from minio.error import S3Error

from .base import CHUNK_SIZE, BlobNotFound, BlobStat, BlobStore, guess_content_type

_MISSING = {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}


class _ObjectStream:
    """Block reader over an S3 response that gives the connection back when closed or exhausted."""

    def __init__(self, response: Any):
        self._response = response
        self._closed = False

    def read(self, size: int = -1) -> bytes:
        return self._response.read() if size is None or size < 0 else self._response.read(size)

    def __iter__(self) -> Iterator[bytes]:
        try:
            while block := self._response.read(CHUNK_SIZE):
                yield block
        finally:
            self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._response.close()
            self._response.release_conn()


class S3BlobStore(BlobStore):
    """Objects in one bucket (created when missing).

    Args:
        endpoint: ``host:port`` of the server.
        access_key, secret_key: Credentials of a user allowed to read and write the bucket.
        bucket: Bucket name.
        secure: Use HTTPS.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False):
        self.bucket = bucket
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    def ensure_bucket(self) -> None:
        """Creates the bucket when it does not exist yet."""
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def put_file(self, key: str, path: Path, content_type: str = "") -> None:
        self._client.fput_object(self.bucket, key, str(path), content_type=content_type or guess_content_type(key))

    def put(self, key: str, data: BinaryIO, size: int, content_type: str = "") -> None:
        self._client.put_object(self.bucket, key, data, length=size, content_type=content_type or guess_content_type(key))

    def stat(self, key: str) -> BlobStat:
        try:
            info = self._client.stat_object(self.bucket, key)
        except S3Error as exc:
            if exc.code in _MISSING:
                raise BlobNotFound(key) from exc
            raise
        return BlobStat(int(info.size or 0), info.content_type or guess_content_type(key), (info.etag or "").strip('"') or None)

    def open(self, key: str, offset: int = 0, length: int | None = None) -> _ObjectStream:
        try:
            response = self._client.get_object(self.bucket, key, offset=offset, length=length or 0)
        except S3Error as exc:
            if exc.code in _MISSING:
                raise BlobNotFound(key) from exc
            raise
        return _ObjectStream(response)

    def delete(self, key: str) -> None:
        self._client.remove_object(self.bucket, key)

    def delete_prefix(self, prefix: str) -> int:
        if not prefix:
            raise ValueError("a non-empty prefix is required")
        names = [o.object_name for o in self._client.list_objects(self.bucket, prefix=prefix, recursive=True)]
        for name in names:
            self._client.remove_object(self.bucket, name)
        return len(names)
