"""Parses and chunks the corpus into a JSONL file (one chunk per line) for offline retrieval evaluation.

The output holds real document text: keep it outside the repository.

    python tools/eval_dump_chunks.py "/path/Du lieu" OUT.jsonl [--workers 16]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.org import UnitTree, place  # noqa: E402
from app.parsing import ParseError, chunk_document, parse_file  # noqa: E402
from tools.survey_parse import find_files  # noqa: E402

ROOT = ""
TREE = UnitTree.load()

def work(path: str) -> list[dict]:
    try:
        doc = parse_file(path)
    except ParseError:
        return []
    except Exception:
        return []
    rel = os.path.relpath(path, ROOT)
    doc_id = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]
    pl = place(TREE, rel.split(os.sep)[:-1], doc.metadata.classification)
    return [{**c.to_dict(), "embed_text": c.embed_text, "unit_id": pl.unit_id, "level": pl.level,
             "doc_type": doc.metadata.doc_type, "title": doc.metadata.title} for c in chunk_document(doc, doc_id)]

def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    ROOT = a.root
    n = 0
    with Pool(a.workers) as pool, open(a.out, "w", encoding="utf-8") as f:
        for rows in pool.imap(work, find_files(a.root), chunksize=4):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    print(n, "chunks ->", a.out)

if __name__ == "__main__":
    main()
