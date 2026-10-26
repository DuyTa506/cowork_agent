"""Dense embedders: a remote OpenAI-compatible server for production, a hashing stand-in for tests."""
from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from .sparse import tokens

class Embedder(Protocol):
    """Dense embedder. Documents and queries are separate calls because some models want an instruction on the query only."""
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class HashEmbedder:
    """Deterministic bag-of-words hashing. No semantics: for tests and for checking the pipeline end to end, not for retrieval quality."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for t in tokens(text):
            h = int.from_bytes(hashlib.blake2b(t.encode("utf-8"), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

class OpenAICompatEmbedder:
    """Calls an OpenAI-compatible /v1/embeddings server (vLLM, TEI...) so the API process loads no model or GPU libraries."""

    def __init__(self, base_url: str, model: str, dim: int, api_key: str = "", query_prefix: str = "",
                 doc_prefix: str = "", batch_size: int = 32, timeout: float = 120.0):
        self.dim, self.model, self.batch_size = dim, model, batch_size
        self.query_prefix, self.doc_prefix = query_prefix, doc_prefix
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {})

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            r = self._client.post("/embeddings", json={"model": self.model, "input": texts[i:i + self.batch_size]})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out += [d["embedding"] for d in data]
        if out and len(out[0]) != self.dim:
            raise ValueError(f"Model trả về vector {len(out[0])} chiều, cấu hình là {self.dim}.")
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self.doc_prefix + t for t in texts] if self.doc_prefix else texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]


class IntramindEmbedder:
    """Calls the serving tier of the intramind stack: ``POST /api/v1/embed {texts, input_type}`` -> ``{embeddings, dimension}``.

    The server applies the model's own query prompt for ``input_type: "query"``, so no prefixes are configured here."""

    def __init__(self, base_url: str, dim: int, api_key: str = "", batch_size: int = 32, timeout: float = 120.0):
        self.dim, self.batch_size = dim, batch_size
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {})

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            r = self._client.post("/api/v1/embed", json={"texts": texts[i:i + self.batch_size], "input_type": input_type})
            r.raise_for_status()
            out += r.json()["embeddings"]
        if out and len(out[0]) != self.dim:
            raise ValueError(f"Máy chủ trả về vector {len(out[0])} chiều, cấu hình là {self.dim}.")
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]
