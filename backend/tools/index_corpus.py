"""Parses, chunks, embeds and indexes every .doc/.docx under a corpus directory into Qdrant.

The unit of each file comes from its folder (this is for the sample corpus; documents uploaded through the app take the
uploader's unit), and a file is secret if its folder is 'văn bản mật' or the document carries a secrecy stamp.

    python tools/index_corpus.py "/path/Du lieu" --collection qk3_smoke --embedder hash [--limit N] [--workers 16]
    python tools/index_corpus.py "/path/Du lieu" --collection qk3_chunks --embedder openai     # EMBEDDING_* from the environment
"""
from __future__ import annotations
import argparse
import hashlib
import os
import sys
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qdrant_client import QdrantClient  # noqa: E402

from app.core import config  # noqa: E402
from app.org import UnitTree, place  # noqa: E402
from app.parsing import ParseError, parse_file  # noqa: E402
from app.search import HashEmbedder, OpenAICompatEmbedder, QdrantIndex  # noqa: E402
from tools.survey_parse import find_files  # noqa: E402

ROOT = ""
TREE = UnitTree.load()

def doc_id_of(path: str) -> str:
    return hashlib.sha1(os.path.relpath(path, ROOT).encode("utf-8")).hexdigest()[:16]

def parse(path: str):
    try:
        doc = parse_file(path)
    except ParseError:
        return None
    except Exception as exc:
        print("  parse bug:", os.path.basename(path), exc, file=sys.stderr)
        return None
    placement = place(TREE, os.path.relpath(path, ROOT).split(os.sep)[:-1], doc.metadata.classification)
    return doc_id_of(path), doc, placement

def make_embedder(kind: str):
    if kind == "hash":
        return HashEmbedder(256)
    if not (config.EMBEDDING_BASE_URL and config.EMBEDDING_MODEL and config.EMBEDDING_DIM):
        sys.exit("Đặt EMBEDDING_BASE_URL, EMBEDDING_MODEL, EMBEDDING_DIM (và EMBEDDING_QUERY_PREFIX nếu model cần).")
    return OpenAICompatEmbedder(config.EMBEDDING_BASE_URL, config.EMBEDDING_MODEL, config.EMBEDDING_DIM,
                                query_prefix=config.EMBEDDING_QUERY_PREFIX)

def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--collection", default=config.QDRANT_COLLECTION)
    ap.add_argument("--embedder", choices=["hash", "openai"], default="openai")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--recreate", action="store_true", help="drop the collection first")
    a = ap.parse_args()
    ROOT = a.root
    files = find_files(a.root)[: a.limit or None]
    client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=120)
    if a.recreate and client.collection_exists(a.collection):
        client.delete_collection(a.collection)
    index = QdrantIndex(client, make_embedder(a.embedder), a.collection)
    index.ensure_collection()
    t0 = time.time()
    docs = chunks = skipped = 0
    with Pool(a.workers) as pool:
        for res in pool.imap(parse, files, chunksize=4):
            if res is None:
                skipped += 1
                continue
            doc_id, doc, placement = res
            chunks += index.index_document(doc_id, doc, placement)
            docs += 1
            if docs % 200 == 0:
                print(f"  {docs} docs, {chunks} chunks, {time.time() - t0:.0f}s", flush=True)
    dt = time.time() - t0
    print(f"indexed {docs} docs ({skipped} unreadable skipped) -> {chunks} chunks in {dt:.0f}s ({chunks / dt:.0f} chunks/s); "
          f"collection has {index.count()} points")

if __name__ == "__main__":
    main()
