"""BM25-style sparse vectors for Qdrant, with no word segmenter.

Vietnamese words are made of space-separated syllables, so unigrams alone match too loosely ('quân' is in a hundred
words) and a segmenter is one more dependency to ship offline. Syllable unigrams plus bigrams approximate word and phrase
matching ('quân khu', 'công binh') well enough, and need nothing but a regex.

The document side carries the BM25 term-frequency weight; the IDF is applied by Qdrant itself (the sparse vector is created
with modifier=IDF), so collection statistics stay correct as documents are added or removed. The query side is binary.
"""
from __future__ import annotations
import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

@dataclass(frozen=True)
class Bm25Config:
    k1: float = 1.2
    b: float = 0.75
    avgdl: float = 220.0  # average chunk length in tokens; the chunker targets ~220 words

def tokens(text: str) -> list[str]:
    return _TOKEN.findall(unicodedata.normalize("NFC", text).lower())

def terms(text: str) -> list[str]:
    toks = tokens(text)
    return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]

def term_id(term: str) -> int:
    """Stable unsigned 32-bit id (Qdrant sparse indices are u32). Not Python's hash(): that changes per process."""
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=4).digest(), "big")

def _merge(weights: dict[int, float]) -> tuple[list[int], list[float]]:
    items = sorted(weights.items())
    return [i for i, _ in items], [w for _, w in items]

def doc_vector(text: str, cfg: Bm25Config = Bm25Config()) -> tuple[list[int], list[float]]:
    dl = len(tokens(text))
    weights: dict[int, float] = {}
    for term, tf in Counter(terms(text)).items():
        w = tf * (cfg.k1 + 1) / (tf + cfg.k1 * (1 - cfg.b + cfg.b * dl / cfg.avgdl))
        i = term_id(term)
        weights[i] = weights.get(i, 0.0) + w  # a hash collision adds, never drops
    return _merge(weights)

def query_vector(text: str) -> tuple[list[int], list[float]]:
    return _merge({term_id(t): 1.0 for t in set(terms(text))})
