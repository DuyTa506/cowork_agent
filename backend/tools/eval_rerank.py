"""Offline evaluation of cross-encoder rerankers on top of the first-stage candidates of `eval_retrieval.py`.

The candidate set and the questions are built exactly like in `eval_retrieval.py` (``--subset`` / ``--max-docs``). First-stage
candidates are the top ``--top`` chunks of BM25 alone or of the RRF fusion of BM25 and the dense model whose cached embeddings are
passed with ``--embed-model``. The reranker then re-orders them; metrics are doc@k / chunk@k over the reranked list. Scores are
cached per (reranker, query, chunk) so an interrupted run resumes.

    python tools/eval_rerank.py CHUNKS.jsonl QUESTIONS.jsonl --cache DIR --embed-model BAAI/bge-m3 --reranker BAAI/bge-reranker-v2-m3
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import random
import sys
import time

import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("qk3_eval_retrieval", os.path.join(_here, "eval_retrieval.py"))
ev = importlib.util.module_from_spec(_spec)
sys.modules["qk3_eval_retrieval"] = ev
_spec.loader.exec_module(ev)

QWEN_INSTRUCT = "Given a Vietnamese question, retrieve the passage of an official military document that answers it"


class CrossEncoderBackend:
    """bge-reranker-v2-m3 and similar sequence-classification rerankers (sentence-transformers CrossEncoder)."""

    def __init__(self, name: str, device: str, max_len: int):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(name, device=device, max_length=max_len)

    def score(self, query: str, docs: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, d) for d in docs], batch_size=8, show_progress_bar=False)]


class QwenBackend:
    """Qwen3-Reranker: a causal LM asked 'yes'/'no'; the score is P(yes) at the last position."""

    PREFIX = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. "
              "Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
    SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def __init__(self, name: str, device: str, max_len: int):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.max_len, self.device = torch, max_len, device
        self.tok = AutoTokenizer.from_pretrained(name, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32).to(device).eval()
        self.yes, self.no = self.tok.convert_tokens_to_ids("yes"), self.tok.convert_tokens_to_ids("no")

    def score(self, query: str, docs: list[str]) -> list[float]:
        torch = self.torch
        out: list[float] = []
        for i in range(0, len(docs), 4):
            texts = [f"{self.PREFIX}<Instruct>: {QWEN_INSTRUCT}\n<Query>: {query}\n<Document>: {d}{self.SUFFIX}" for d in docs[i:i + 4]]
            enc = self.tok(texts, padding=True, truncation=True, max_length=self.max_len, return_tensors="pt").to(self.device)
            with torch.no_grad():
                logits = self.model(**enc).logits[:, -1, :]
            pair = torch.stack([logits[:, self.no], logits[:, self.yes]], dim=1).float()
            out += torch.softmax(pair, dim=1)[:, 1].tolist()
        return out


class JinaBackend:
    """jina-reranker-v3: listwise, scores all documents of a query in one pass (remote code)."""

    def __init__(self, name: str, device: str, max_len: int):
        import torch
        from transformers import AutoModel
        self.max_len = max_len
        self.model = AutoModel.from_pretrained(name, trust_remote_code=True, torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32).to(device).eval()

    def score(self, query: str, docs: list[str]) -> list[float]:
        scores = [0.0] * len(docs)
        for row in self.model.rerank(query, docs, max_doc_length=self.max_len):
            scores[int(row["index"])] = float(row["relevance_score"])
        return scores


def backend_for(name: str):
    low = name.lower()
    if "qwen3-reranker" in low:
        return QwenBackend
    if "jina-reranker-v3" in low:
        return JinaBackend
    return CrossEncoderBackend


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks")
    ap.add_argument("questions")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--embed-model", default="", help="dense model whose cached embeddings feed the hybrid first stage (empty: BM25 only)")
    ap.add_argument("--reranker", required=True)
    ap.add_argument("--top", type=int, default=20, help="first-stage candidates handed to the reranker")
    ap.add_argument("--subset", type=int, default=2000)
    ap.add_argument("--max-docs", type=int, default=200)
    ap.add_argument("--limit", type=int, default=0, help="evaluate only every n-th question to the given total (0: all)")
    ap.add_argument("--max-len", type=int, default=512, help="tokens per query+passage pair")
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()

    chunks = [json.loads(l) for l in open(a.chunks, encoding="utf-8")]
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")]
    qdocs = sorted({q["doc_id"] for q in qs})[: a.max_docs]
    qs = [q for q in qs if q["doc_id"] in set(qdocs)]
    gold_docs = {q["doc_id"] for q in qs}
    others = [i for i, c in enumerate(chunks) if c["doc_id"] not in gold_docs]
    extra = set(random.Random(13).sample(others, min(a.subset, len(others))))
    keep = [i for i, c in enumerate(chunks) if c["doc_id"] in gold_docs or i in extra]
    cands = [chunks[i] for i in keep]
    pos = {c["id"]: i for i, c in enumerate(cands)}
    qs_all = [q for q in qs if q["chunk_id"] in pos]
    texts_all = [q["question"] for q in qs_all]
    qhash = hashlib.sha1("\n".join(texts_all).encode("utf-8")).hexdigest()[:10]  # same key as eval_retrieval's query cache
    if a.limit and a.limit < len(qs_all):
        step = len(qs_all) / a.limit
        sel = [int(i * step) for i in range(a.limit)]
    else:
        sel = list(range(len(qs_all)))
    qs = [qs_all[i] for i in sel]
    texts = [q["question"] for q in qs]
    gold_chunk = [pos[q["chunk_id"]] for q in qs]
    gold_doc = [q["doc_id"] for q in qs]
    doc_of = [c["doc_id"] for c in cands]

    bm_lists = [ev.ranks_of(s) for s in ev.bm25_scores(cands, texts)]
    first = [list(b[:a.top]) for b in bm_lists]
    stage = "bm25"
    if a.embed_model:
        tag = a.embed_model.replace("/", "__")
        skey = hashlib.sha1("\n".join(c["id"] for c in cands).encode()).hexdigest()[:8]
        docs = np.load(f"{a.cache}/{tag}.docs.{skey}.npy")
        qv = np.load(f"{a.cache}/{tag}.q.{qhash}.npy")[sel]
        dense = [ev.ranks_of(docs @ v) for v in qv]
        first = [ev.rrf([d, b], top=a.top) for d, b in zip(dense, bm_lists)]
        stage = f"rrf(bm25,{a.embed_model})"

    base = ev.metrics(first, gold_chunk, doc_of, gold_doc)
    recall = float(np.mean([g in set(f) for f, g in zip(first, gold_chunk)]))
    doc_recall = float(np.mean([any(doc_of[i] == gd for i in f) for f, gd in zip(first, gold_doc)]))

    cache_file = f"{a.cache}/rerank.{a.reranker.replace('/', '__')}.{a.top}.{a.max_len}.jsonl"
    done: dict[str, list[float]] = {}
    if os.path.exists(cache_file):
        for l in open(cache_file, encoding="utf-8"):
            r = json.loads(l)
            done[r["q"]] = r["s"]
    backend = None
    t0, scored = time.time(), 0
    ranked: list[list[int]] = []
    with open(cache_file, "a", encoding="utf-8") as out:
        for n, (q, f) in enumerate(zip(texts, first)):
            key = hashlib.sha1((q + "|" + ",".join(cands[i]["id"] for i in f)).encode()).hexdigest()[:16]
            if key not in done:
                if backend is None:
                    backend = backend_for(a.reranker)(a.reranker, a.device, a.max_len)
                done[key] = backend.score(q, [cands[i]["embed_text"] for i in f])
                out.write(json.dumps({"q": key, "s": done[key]}) + "\n")
                out.flush()
                scored += 1
                if scored % 20 == 0:
                    print(f"  {n + 1}/{len(texts)} {(time.time() - t0) / scored:.1f}s/query", file=sys.stderr, flush=True)
            order = np.argsort(-np.asarray(done[key]), kind="stable")
            ranked.append([f[j] for j in order])
    res = {
        "reranker": a.reranker, "first_stage": stage, "top": a.top, "questions": len(qs), "max_len": a.max_len,
        "first_stage_recall_in_top": {"chunk": round(recall, 4), "doc": round(doc_recall, 4)},
        "before": base, "after": ev.metrics(ranked, gold_chunk, doc_of, gold_doc),
        "s_per_query": round((time.time() - t0) / max(scored, 1), 2) if scored else None,
    }
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
