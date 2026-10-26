"""HTTP replies for objects in the store: streamed (never held whole in memory), with ``Range`` support so a PDF viewer can fetch
only the pages it shows."""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from app import storage
from app.core.errors import NotFound

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _disposition(name: str, inline: bool) -> str:
    return f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name)}"


def blob_response(request: Request, key: str, filename: str, *, inline: bool = False, cacheable: bool = False) -> Response:
    """Replies with the object under `key`: 200 with the whole body, 206 for a satisfiable single byte range, 416 for an unsatisfiable one.

    Raises:
        NotFound: the object is not in the store.
    """
    store = storage.get_store()
    try:
        info = store.stat(key)
    except storage.BlobNotFound as exc:
        raise NotFound("Tệp gốc không còn trong kho lưu trữ.") from exc
    headers = {"Content-Disposition": _disposition(filename, inline), "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600" if cacheable else "private, no-store",
               "X-Content-Type-Options": "nosniff"}
    if info.etag:
        headers["ETag"] = f'"{info.etag}"'
    match = _RANGE.match(request.headers.get("range", "").strip())
    if match and (match.group(1) or match.group(2)):
        if match.group(1):
            start = int(match.group(1))
            end = min(int(match.group(2)), info.size - 1) if match.group(2) else info.size - 1
        else:  # "-N": the last N bytes
            start, end = max(info.size - int(match.group(2)), 0), info.size - 1
        if start >= info.size or start > end:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{info.size}"})
        length = end - start + 1
        headers.update({"Content-Range": f"bytes {start}-{end}/{info.size}", "Content-Length": str(length)})
        return StreamingResponse(store.open(key, start, length), status_code=206, media_type=info.content_type, headers=headers)
    headers["Content-Length"] = str(info.size)
    return StreamingResponse(store.open(key), media_type=info.content_type, headers=headers)
