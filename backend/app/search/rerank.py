"""Rerankers: re-score retrieved passages against the query with a cross-encoder served over HTTP.

Three wire protocols are supported:

* ``cohere``    — ``POST /rerank {"model", "query", "documents": [...]}`` (vLLM, Jina, Cohere-compatible servers)
* ``tei``       — ``POST /rerank {"query", "texts": [...]}`` (Hugging Face text-embeddings-inference)
* ``intramind`` — ``POST /api/v1/rerank {"query", "documents": [...], "top_k"}`` (the serving tier of the intramind stack)

All answer with ``[{"index": i, "score" | "relevance_score": s}, ...]`` (TEI as a bare list, the others under ``results``).
"""
from __future__ import annotations

from typing import Protocol

import httpx

PROTOCOLS = ("cohere", "tei", "intramind")
_PATH = {"cohere": "/rerank", "tei": "/rerank", "intramind": "/api/v1/rerank"}


class Reranker(Protocol):
    """Scores passages for a query; a higher score is more relevant."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Returns one score per document, in the order given."""
        ...


class HttpReranker:
    """Reranker backed by a remote server speaking one of `PROTOCOLS`."""

    def __init__(self, base_url: str, model: str, protocol: str = "cohere", api_key: str = "", timeout: float = 60.0):
        if protocol not in PROTOCOLS:
            raise ValueError(f"Giao thức rerank không hợp lệ: {protocol!r}")
        self.model, self.protocol = model, protocol
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {})

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Sends one request for all `documents` and maps the response back to input order."""
        if not documents:
            return []
        if self.protocol == "cohere":
            body = {"model": self.model, "query": query, "documents": documents}
        elif self.protocol == "tei":
            body = {"query": query, "texts": documents}
        else:
            body = {"query": query, "documents": documents, "top_k": len(documents)}
        response = self._client.post(_PATH[self.protocol], json=body)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results", payload.get("data", [])) if isinstance(payload, dict) else payload
        scores = [0.0] * len(documents)
        for row in rows:
            scores[int(row["index"])] = float(row.get("relevance_score", row.get("score", 0.0)))
        return scores


def make_reranker(values: dict) -> Reranker | None:
    """Builds the reranker described by the ``rerank`` settings section, or None when it is disabled or incomplete."""
    if not (values.get("enabled") and values.get("base_url")):
        return None
    return HttpReranker(values["base_url"], values.get("model", ""), values.get("protocol", "cohere"), values.get("api_key", ""))
