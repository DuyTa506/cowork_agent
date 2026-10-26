"""How well units are recognised across a corpus: from the folder path, and against the agency block at the top of each document.

    python tools/survey_units.py "/path/Du lieu" survey.jsonl     # survey.jsonl = output of tools/survey_parse.py
"""
from __future__ import annotations
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.org import UnitTree  # noqa: E402

EXT = (".doc", ".docx", ".pdf")

def main() -> None:
    root, survey = sys.argv[1], sys.argv[2]
    tree = UnitTree.load()
    files = []
    for r, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d != "phan_loai_pdf"]
        files += [os.path.join(r, f) for f in fs if f.lower().endswith(EXT) and not f.startswith("~$")]
    by_path = {p: tree.resolve_path(os.path.relpath(p, root).split(os.sep)[:-1]) for p in files}
    n = len(files)
    resolved = [p for p, m in by_path.items() if m.unit_id]
    print(f"files {n}: unit from folder {len(resolved)} ({100 * len(resolved) // n}%), none {n - len(resolved)}, in a 'văn bản mật' folder {sum(m.secret_folder for m in by_path.values())}")
    depth = collections.Counter(tree.get(m.unit_id).type for m in by_path.values() if m.unit_id)
    print("resolved to:", dict(depth))
    lost = collections.Counter(os.path.relpath(p, root).split(os.sep)[0] for p, m in by_path.items() if not m.unit_id)
    print("unresolved by top folder:", lost.most_common(6))

    rows = [json.loads(l) for l in open(survey, encoding="utf-8")]
    rows = [r for r in rows if "error" not in r and r["path"] in by_path]
    same = more_general = contradict = ambiguous = nohdr = 0
    ex_contra, ex_unknown = [], collections.Counter()
    for r in rows:
        f = by_path[r["path"]].unit_id
        if not r["agency"]:
            nohdr += 1
            continue
        h = tree.resolve_header(r["agency"])
        if h.unit_id is None:
            if h.candidates:
                ambiguous += 1
            else:
                ex_unknown[r["agency"]] += 1
            continue
        if not f:
            continue
        if h.unit_id == f:
            same += 1
        elif h.unit_id in tree.ancestors(f):
            more_general += 1  # the header names an agency above the folder's unit (e.g. BỘ THAM MƯU vs Phòng Công binh)
        else:
            contradict += 1
            if len(ex_contra) < 8:
                ex_contra.append((os.path.relpath(r["path"], root)[:55], tree.get(f).name, "<-> header:", tree.get(h.unit_id).name))
    print(f"\nheader vs folder over {len(rows)} parsed docs: header empty {nohdr} | header ambiguous {ambiguous} | header unknown {sum(ex_unknown.values())}")
    print(f"  same unit {same} | header is an ancestor (coarser) {more_general} | CONTRADICTS the folder {contradict}")
    for e in ex_contra:
        print("   ", *e)
    print("most frequent header agencies not in the unit list:", ex_unknown.most_common(12))

if __name__ == "__main__":
    main()
