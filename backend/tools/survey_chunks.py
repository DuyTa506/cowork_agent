"""Chunks every .doc/.docx under a corpus directory and reports size distribution and content-conservation checks.

    python tools/survey_chunks.py "/path/Du lieu" [--limit N] [--jobs 16] [--target 220 --max 380 --min 60]
"""
from __future__ import annotations
import argparse
import os
import statistics
import sys
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.parsing import ChunkConfig, ParseError, chunk_document, parse_file  # noqa: E402
from tools.survey_parse import find_files  # noqa: E402

CFG = ChunkConfig()

def work(path: str) -> dict:
    try:
        doc = parse_file(path)
    except ParseError:
        return {"skip": True}
    except Exception as exc:
        return {"path": path, "bug": f"{type(exc).__name__}: {exc}"[:160]}
    chunks = chunk_document(doc, "x", CFG)
    body = [c for c in chunks if c.part != "meta"]
    doc_words = len(doc.text().split())
    kept = sum(len(c.text.split()) for c in body)
    # table pieces repeat their header row, so the chunks may hold slightly more words than the document
    return {"path": path, "n": len(chunks), "sizes": [c.words for c in body], "doc_words": doc_words, "kept": kept,
            "empty": sum(1 for c in chunks if not c.text.strip()),
            "has_table": any(b.kind == "table" for s in doc.root.walk() for b in s.blocks)}

def pct(xs: list[int], q: float) -> int:
    xs = sorted(xs)
    return xs[min(int(len(xs) * q), len(xs) - 1)] if xs else 0

def main() -> None:
    global CFG
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--target", type=int, default=CFG.target)
    ap.add_argument("--max", type=int, default=CFG.max)
    ap.add_argument("--min", type=int, default=CFG.min)
    a = ap.parse_args()
    CFG = ChunkConfig(target=a.target, max=a.max, min=a.min)
    files = find_files(a.root)[: a.limit or None]
    t0 = time.time()
    with Pool(a.jobs) as pool:
        rows = pool.map(work, files, chunksize=8)
    bugs = [r for r in rows if "bug" in r]
    ok = [r for r in rows if "n" in r]
    sizes = [s for r in ok for s in r["sizes"]]
    print(f"docs {len(ok)} (unreadable skipped {sum(1 for r in rows if r.get('skip'))}, bugs {len(bugs)})  chunks {sum(r['n'] for r in ok)}  wall {time.time() - t0:.1f}s")
    for r in bugs[:5]:
        print("  BUG", os.path.basename(r["path"]), r["bug"])
    print(f"body chunk words: median {statistics.median(sizes):.0f}  p10 {pct(sizes, .1)}  p90 {pct(sizes, .9)}  p99 {pct(sizes, .99)}  max {max(sizes)}")
    multi = [r for r in ok if len(r["sizes"]) > 1]
    small = sum(1 for r in multi for s in r["sizes"] if s < CFG.min)
    print(f"chunks < {CFG.min} words in multi-chunk docs: {small} ({100 * small / max(sum(len(r['sizes']) for r in multi), 1):.1f}%)")
    print(f"chunks > {CFG.max} words: {sum(1 for s in sizes if s > CFG.max)}   empty chunks: {sum(r['empty'] for r in ok)}")
    no_body = [r for r in ok if not r["sizes"]]
    print(f"docs with no body chunk: {len(no_body)}")
    lost = [r for r in ok if r["kept"] < r["doc_words"]]
    dup = [r for r in ok if r["kept"] > r["doc_words"] and not r["has_table"]]
    print(f"conservation: chunks hold FEWER words than the document in {len(lost)} docs; MORE (no table) in {len(dup)} docs")
    for r in (lost + dup)[:6]:
        print(f"  {os.path.basename(r['path'])[:60]}: doc {r['doc_words']} vs chunks {r['kept']}")

if __name__ == "__main__":
    main()
