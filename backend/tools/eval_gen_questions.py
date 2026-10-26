"""Writes evaluation questions for sampled chunks with an OpenAI-compatible LLM (QK3_LLM_BASE_URL / QK3_LLM_MODEL / QK3_LLM_KEY).

Questions are paraphrased on purpose: they must not repeat the document title or long phrases of the passage, otherwise the test
only measures lexical overlap.

    python tools/eval_gen_questions.py CHUNKS.jsonl OUT.jsonl [--n 400] [--per-chunk 2] [--seed 7] [--workers 12]
"""
from __future__ import annotations
import argparse
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

PROMPT = """Dưới đây là một đoạn trích từ văn bản của cơ quan quân đội. Hãy viết {k} câu hỏi mà một cán bộ, nhân viên có thể hỏi hệ thống tra cứu để tìm đúng đoạn này.

Yêu cầu:
- Mỗi câu hỏi trả lời được bằng chính nội dung đoạn trích, hỏi về một ý cụ thể (số liệu, thời hạn, trách nhiệm, điều kiện, nội dung quy định...).
- Diễn đạt lại bằng từ ngữ của bạn, KHÔNG chép nguyên cụm từ dài hoặc tiêu đề văn bản; không nhắc "đoạn trích", "văn bản này", "theo đoạn trên".
- Câu hỏi phải tự đứng được (hiểu được khi không có đoạn trích), tự nhiên như người thật hỏi.
- Chỉ trả về JSON: {{"questions": ["...", "..."]}}

Đoạn trích (thuộc: {context}):
\"\"\"
{text}
\"\"\""""

def ask(client: httpx.Client, base: str, model: str, key: str, row: dict, k: int) -> list[str]:
    body = {"model": model, "temperature": 0.7, "max_tokens": 2500,  # the model reasons first; a small budget leaves the answer empty
            
            "messages": [{"role": "user", "content": PROMPT.format(k=k, context=row["context"][:200], text=row["text"][:2500])}]}
    try:
        r = client.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=180)
        txt = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        qs = json.loads(m.group(0))["questions"] if m else []
    except Exception:
        return []
    return [q.strip() for q in qs if isinstance(q, str) and 15 <= len(q.strip()) <= 300][:k]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--per-chunk", type=int, default=2)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.chunks, encoding="utf-8")]
    pool = [r for r in rows if r["part"] != "meta" and r["words"] >= 80]
    by_doc: dict[str, list[dict]] = {}
    for r in pool:
        by_doc.setdefault(r["doc_id"], []).append(r)
    rng = random.Random(a.seed)
    docs = list(by_doc)
    rng.shuffle(docs)
    sample = [rng.choice(by_doc[d]) for d in docs[: a.n]]  # one chunk per document: no document dominates
    base, model, key = os.environ["QK3_LLM_BASE_URL"].rstrip("/"), os.environ["QK3_LLM_MODEL"], os.environ.get("QK3_LLM_KEY", "sk-dummy-noauth")
    n = done = 0
    with httpx.Client() as client, ThreadPoolExecutor(a.workers) as ex, open(a.out, "w", encoding="utf-8") as f:
        # results are written as they arrive, so an interrupted run still leaves usable questions
        for r, qs in zip(sample, ex.map(lambda r: ask(client, base, model, key, r, a.per_chunk), sample)):
            done += 1
            for q in qs:
                f.write(json.dumps({"question": q, "chunk_id": r["id"], "doc_id": r["doc_id"], "unit_id": r["unit_id"]}, ensure_ascii=False) + "\n")
                n += 1
            f.flush()
            if done % 25 == 0:
                print(f"  {done}/{len(sample)} chunks, {n} questions", flush=True)
    print(f"{len(sample)} chunks sampled, {n} questions -> {a.out}")

if __name__ == "__main__":
    main()
