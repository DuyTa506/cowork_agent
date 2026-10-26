"""Offline retrieval evaluation of embedding models on the whole chunked corpus (needs torch + sentence-transformers).

Every chunk of the corpus is a candidate, so the other chunks of the same document are the hard negatives. Reports, per model,
recall@k and MRR for dense alone, BM25 alone (the same syllable uni+bigram scheme as the Qdrant sparse vector) and their RRF
fusion (k=60), at chunk level (the gold chunk) and at document level (any chunk of the gold document).

    python tools/eval_retrieval.py CHUNKS.jsonl QUESTIONS.jsonl --cache DIR --model NAME [--query-prompt "..."] [--doc-prompt "..."]
"""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
import time
from collections import defaultdict

import numpy as np

import importlib.util  # noqa: E402

# sparse.py is loaded by path: importing app.search would pull in the parser (doccheck), which the torch venv does not have
_spec = importlib.util.spec_from_file_location(
    "qk3_sparse", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "search", "sparse.py"))
_sparse = importlib.util.module_from_spec(_spec)
sys.modules["qk3_sparse"] = _sparse  # dataclasses look the module up by name
_spec.loader.exec_module(_sparse)
Bm25Config, doc_vector, query_vector = _sparse.Bm25Config, _sparse.doc_vector, _sparse.query_vector

def bm25_scores(chunks: list[dict], queries: list[str], cfg: Bm25Config = Bm25Config()):
    """Inverted index with Qdrant's IDF modifier: idf = ln(1 + (N - n + 0.5) / (n + 0.5))."""
    postings: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for i, c in enumerate(chunks):
        idx, val = doc_vector(c["embed_text"], cfg)
        for t, w in zip(idx, val):
            postings[t].append((i, w))
    n = len(chunks)
    idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in postings.items()}
    for q in queries:
        sc = np.zeros(n, dtype=np.float32)
        for t in query_vector(q)[0]:
            for i, w in postings.get(t, ()):
                sc[i] += w * idf[t]
        yield sc

def repair_remote_code(model) -> None:
    """gte-multilingual-base's remote code breaks under transformers 5: its non-persistent buffers (RoPE tables, position_ids) are
    left uninitialised and get_extended_attention_mask no longer exists. Rebuild them after loading."""
    import torch
    for mod in model.modules():
        if hasattr(mod, "_set_cos_sin_cache") and hasattr(mod, "inv_freq"):
            mod.inv_freq = 1.0 / (mod.base ** (torch.arange(0, mod.dim, 2).float() / mod.dim))
            mod._set_cos_sin_cache(int(mod.max_seq_len_cached), mod.inv_freq.device, torch.float32)
        if "position_ids" in getattr(mod, "_buffers", {}):
            mod.position_ids = torch.arange(mod.position_ids.numel())
    cls = type(model[0].auto_model)
    if not hasattr(cls, "get_extended_attention_mask"):
        def get_extended_attention_mask(self, attention_mask, input_shape, device=None, dtype=None):
            dtype = dtype or torch.float32
            return (1.0 - attention_mask[:, None, None, :].to(dtype)) * torch.finfo(dtype).min
        cls.get_extended_attention_mask = get_extended_attention_mask

def ranks_of(scores: np.ndarray, top: int = 50) -> np.ndarray:
    k = min(top, scores.shape[0])
    part = np.argpartition(-scores, k - 1)[:k]
    return part[np.argsort(-scores[part])]

def rrf(lists: list[np.ndarray], k: int = 60, top: int = 50) -> list[int]:
    acc: dict[int, float] = defaultdict(float)
    for lst in lists:
        for r, i in enumerate(lst):
            acc[int(i)] += 1.0 / (k + r + 1)
    return sorted(acc, key=lambda i: -acc[i])[:top]

def metrics(order: list[list[int]], gold_chunk: list[int], doc_of: list[str], gold_doc: list[str]) -> dict[str, float]:
    out = {f"{lvl}@{k}": 0.0 for lvl in ("chunk", "doc") for k in (1, 5, 10)}
    out["chunk_mrr10"] = 0.0
    for ranked, g, gd in zip(order, gold_chunk, gold_doc):
        top = list(ranked)[:10]
        for k in (1, 5, 10):
            out[f"chunk@{k}"] += g in top[:k]
            out[f"doc@{k}"] += any(doc_of[i] == gd for i in top[:k])
        if g in top:
            out["chunk_mrr10"] += 1.0 / (top.index(g) + 1)
    n = len(order)
    return {k: round(v / n, 4) for k, v in out.items()}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks")
    ap.add_argument("questions")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--query-prompt", default="")
    ap.add_argument("--doc-prompt", default="")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--subset", type=int, default=0, help="candidates: chunks of the gold documents + this many random other chunks")
    ap.add_argument("--max-docs", type=int, default=0, help="use questions of only this many gold documents")
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--trust-remote-code", action="store_true")
    a = ap.parse_args()
    chunks = [json.loads(l) for l in open(a.chunks, encoding="utf-8")]
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")]
    all_chunks = chunks
    keep = list(range(len(chunks)))
    if a.max_docs:  # fewer gold documents: fewer questions and a smaller candidate set
        qdocs = sorted({q["doc_id"] for q in qs})[: a.max_docs]
        qs = [q for q in qs if q["doc_id"] in set(qdocs)]
    if a.subset:  # candidates = every chunk of the gold documents (same-document hard negatives) + a fixed random sample of others
        gold_docs = {q["doc_id"] for q in qs}
        others = [i for i, c in enumerate(all_chunks) if c["doc_id"] not in gold_docs]
        extra = set(random.Random(13).sample(others, min(a.subset, len(others))))
        keep = [i for i, c in enumerate(all_chunks) if c["doc_id"] in gold_docs or i in extra]
    chunks = [all_chunks[i] for i in keep]
    pos = {c["id"]: i for i, c in enumerate(chunks)}
    qs = [q for q in qs if q["chunk_id"] in pos]
    gold_chunk = [pos[q["chunk_id"]] for q in qs]
    gold_doc = [q["doc_id"] for q in qs]
    doc_of = [c["doc_id"] for c in chunks]
    texts = [q["question"] for q in qs]

    os.makedirs(a.cache, exist_ok=True)
    tag = a.model.replace("/", "__")
    import hashlib
    qhash = hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:10]
    f_full = f"{a.cache}/{tag}.docs.npy"
    subset_key = hashlib.sha1("\n".join(c["id"] for c in chunks).encode()).hexdigest()[:8]
    f_docs = f"{a.cache}/{tag}.docs.{subset_key}.npy" if a.subset else f_full
    f_q = f"{a.cache}/{tag}.q.{qhash}.npy"  # documents and questions are cached apart
    if a.subset and not os.path.exists(f_docs) and os.path.exists(f_full):  # reuse a full-corpus run instead of re-encoding
        np.save(f_docs, np.load(f_full)[keep])
    t_enc = 0.0
    if not (os.path.exists(f_docs) and os.path.exists(f_q)):
        import torch
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(a.model, device=a.device, trust_remote_code=a.trust_remote_code, model_kwargs={"torch_dtype": torch.bfloat16 if a.device == "cuda" else torch.float32})
        if a.trust_remote_code:
            repair_remote_code(m)
        m.max_seq_length = a.max_len
        if not os.path.exists(f_docs):
            t0 = time.time()
            order = sorted(range(len(chunks)), key=lambda i: len(chunks[i]["embed_text"]))  # length-sorted batches: less padding
            d = m.encode([a.doc_prompt + chunks[i]["embed_text"] for i in order], batch_size=a.batch, normalize_embeddings=True,
                         convert_to_numpy=True, show_progress_bar=False)
            docs = np.zeros_like(d)
            docs[order] = d
            t_enc = time.time() - t0
            np.save(f_docs, docs.astype(np.float32))
        if not os.path.exists(f_q):
            qv = m.encode([a.query_prompt + t for t in texts], batch_size=64, normalize_embeddings=True, convert_to_numpy=True,
                          show_progress_bar=False)
            np.save(f_q, qv.astype(np.float32))
    docs, qv = np.load(f_docs), np.load(f_q)

    dense_lists = [ranks_of(docs @ v) for v in qv]
    bm_lists = [ranks_of(s) for s in bm25_scores(chunks, texts)]
    res = {
        "model": a.model, "dim": int(docs.shape[1]), "questions": len(qs), "corpus_chunks": len(chunks), "encode_s": round(t_enc, 1),
        "dense": metrics([list(x) for x in dense_lists], gold_chunk, doc_of, gold_doc),
        "bm25": metrics([list(x) for x in bm_lists], gold_chunk, doc_of, gold_doc),
        "hybrid": metrics([rrf([d, b]) for d, b in zip(dense_lists, bm_lists)], gold_chunk, doc_of, gold_doc),
    }
    print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    main()
