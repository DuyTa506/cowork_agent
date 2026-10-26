"""Learns each unit's writing style from the documents in the search index, for the drafting assistant (`canvas_style`) and for
the header of new drafts (see app/drafting/style_mining.py for what is learnt and how documents are kept out of it).

    python tools/build_style_profiles.py [--collection qk3_chunks_xxxxxxxx] [--out path/profiles.json]

Run it again after a large import. The file it writes (DATA_DIR/style/profiles.json by default) is read on the assistant's next
call; secret documents are not used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qdrant_client import QdrantClient  # noqa: E402

from app.core import config  # noqa: E402
from app.drafting import style, style_mining  # noqa: E402
from app.org import UnitTree  # noqa: E402

FIELDS = ["doc_id", "chunk_index", "part", "text", "level", "doc_type", "unit_id", "symbol", "issuing_agency", "date"]


def _collection() -> str:
    from app.services import settings

    return settings.collection_name(settings.cache.get("embedding"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default="", help="Qdrant collection (default: the one of the configured embedding)")
    ap.add_argument("--out", type=Path, default=None, help=f"output file (default: {style.profile_path()})")
    args = ap.parse_args()
    started = time.monotonic()
    collection = args.collection or _collection()
    client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)
    chunks: dict[str, list[dict]] = defaultdict(list)
    offset = None
    while True:
        points, offset = client.scroll(collection, limit=2048, offset=offset, with_payload=FIELDS, with_vectors=False)
        for point in points:
            chunks[point.payload["doc_id"]].append(point.payload)
        if offset is None:
            break
    samples = [s for s in (style_mining.sample(c) for c in chunks.values()) if s]
    data = style_mining.build(samples, UnitTree.load())
    out = args.out or style.profile_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_suffix(".tmp")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    partial.replace(out)
    kinds = sum(len(u.get("kinds", {})) for u in data["units"].values())
    print(f"{len(chunks)} văn bản trong chỉ mục, {len(samples)} dùng được (không tính văn bản mật); "
          f"{len(data['units'])} đơn vị, {kinds} hồ sơ đơn vị × loại văn bản -> {out} ({time.monotonic() - started:.0f} giây)")


if __name__ == "__main__":
    main()
