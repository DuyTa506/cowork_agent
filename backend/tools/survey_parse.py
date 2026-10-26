"""Parses every .doc/.docx under a corpus directory and reports how many metadata fields were recovered.

    python tools/survey_parse.py "/path/Du lieu" --out survey.jsonl [--limit N] [--jobs 16]
"""
from __future__ import annotations
import argparse
import collections
import json
import os
import sys
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.parsing import ParseError, parse_file  # noqa: E402

EXT = (".doc", ".docx")
SKIP_DIRS = {"phan_loai_pdf"}  # copies of the PDFs, sorted by text quality

def find_files(root: str) -> list[str]:
    out = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        out += [os.path.join(r, f) for f in files if f.lower().endswith(EXT) and not f.startswith("~$")]
    return sorted(out)

def work(path: str) -> dict:
    t = time.time()
    try:
        d = parse_file(path)
    except ParseError as exc:
        return {"path": path, "error": str(exc)[:200]}
    except Exception as exc:  # a parser bug: keep going, report it
        return {"path": path, "error": f"BUG {type(exc).__name__}: {exc}"[:200]}
    m = d.metadata
    secs = list(d.root.walk())[1:]
    return {
        "path": path, "format": d.format, "sec": round(time.time() - t, 3), "warnings": d.warnings,
        "doc_type": m.doc_type, "code": m.doc_type_code, "number": m.number, "symbol": m.symbol, "date": m.date,
        "date_text": bool(m.date_text), "agency": m.issuing_agency, "title": m.title, "signer": m.signer_name,
        "recipients_to": len(m.recipients_to), "distribution": len(m.distribution), "legal_bases": len(m.legal_bases),
        "sections": collections.Counter(s.kind for s in secs), "chars": len(d.text()), "draft": m.is_draft,
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default="survey.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    files = find_files(a.root)
    if a.limit:
        files = files[: a.limit]
    t0 = time.time()
    with Pool(a.jobs) as pool:
        rows = pool.map(work, files, chunksize=8)
    with open(a.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    print(f"files {n}  parsed {len(ok)}  errors {n - len(ok)}  wall {time.time() - t0:.1f}s")
    for k, v in collections.Counter(r["error"].split(":")[0][:60] for r in rows if "error" in r).most_common(6):
        print(f"   error x{v}: {k}")
    def pct(label, pred):
        c = sum(1 for r in ok if pred(r))
        print(f"  {label:<26}{c:>5}  {100 * c / max(len(ok), 1):5.1f}%")
    print("field coverage (of parsed):")
    pct("doc_type", lambda r: r["doc_type"]); pct("issuing agency", lambda r: r["agency"])
    pct("symbol", lambda r: r["symbol"]); pct("number filled", lambda r: r["number"])
    pct("date (full)", lambda r: r["date"]); pct("date line found", lambda r: r["date_text"])
    pct("title", lambda r: r["title"]); pct("signer", lambda r: r["signer"])
    pct("distribution", lambda r: r["distribution"]); pct("has sections", lambda r: sum(r["sections"].values()) > 0)
    print("doc_type:", collections.Counter(r["doc_type"] or "(none)" for r in ok).most_common(14))
    print("warnings:", collections.Counter(w for r in ok for w in r["warnings"]).most_common(6))
    print("section kinds:", sum((collections.Counter(r["sections"]) for r in ok), collections.Counter()).most_common())
    slow = sorted(ok, key=lambda r: -r["sec"])[:3]
    print("slowest:", [(os.path.basename(r["path"])[:40], r["sec"]) for r in slow])

if __name__ == "__main__":
    main()
