"""QK3 serving adapter: the /api/v1/embed and /api/v1/rerank wire protocol on top of two vLLM pooling servers.

Same contract as mta-ai-serving-intramind (:5003), so QK3 needs no code change:
  POST /api/v1/embed   {texts: [str], input_type: "document"|"query"}  -> {embeddings, dimension, model}
  POST /api/v1/rerank  {query, documents: [str], top_k: int|null}       -> {results: [{index, score}]}
  GET  /health
Differences from the intramind layer, on purpose: no attempt-id / revision headers (managed termination contract is
not implemented), and no TTS/STT/diarization routes.
"""
import asyncio
import math
import os
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

EMBED_URL = os.environ.get("EMBED_BACKEND_URL", "http://127.0.0.1:8202")
RERANK_URL = os.environ.get("RERANK_BACKEND_URL", "http://127.0.0.1:8203")
EMBED_MODEL = os.environ.get("EMBED_MODEL_NAME", "microsoft/harrier-oss-v1-270m")
RERANK_MODEL = os.environ.get("RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
EMBED_MAX_TOKENS = int(os.environ.get("EMBED_MAX_TOKENS", "32768"))
EMBED_MAX_BATCH = int(os.environ.get("EMBED_MAX_BATCH", "64"))
RERANK_MAX_TOKENS = int(os.environ.get("RERANK_MAX_TOKENS", "8192"))
RERANK_MAX_BATCH = int(os.environ.get("RERANK_MAX_BATCH", "100"))
QUERY_PREFIX = os.environ.get(
    "EMBED_QUERY_PREFIX",
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: ",
).replace("\\n", "\n")
TIMEOUT = float(os.environ.get("BACKEND_TIMEOUT", "120"))

app = FastAPI(title="qk3-serving adapter")
# overridable in tests
_transport: Optional[httpx.AsyncBaseTransport] = None


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, transport=_transport)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1)
    input_type: Literal["document", "query"] = "document"


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dimension: int
    model: str


class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(default_factory=list)
    top_k: Optional[int] = None


class RerankResultItem(BaseModel):
    index: int
    score: float


class RerankResponse(BaseModel):
    results: list[RerankResultItem]


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return v if n == 0 or abs(n - 1.0) < 1e-3 else [x / n for x in v]


@app.post("/api/v1/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    texts = [QUERY_PREFIX + t for t in req.texts] if req.input_type == "query" else list(req.texts)
    batches = [texts[i:i + EMBED_MAX_BATCH] for i in range(0, len(texts), EMBED_MAX_BATCH)]
    out: list[list[float]] = []
    try:
        async with client() as c:
            for b in batches:
                r = await c.post(f"{EMBED_URL}/v1/embeddings", json={
                    "model": EMBED_MODEL, "input": b, "truncate_prompt_tokens": EMBED_MAX_TOKENS})
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                out.extend(_unit(d["embedding"]) for d in data)
    except Exception as e:  # backend down or rejected the request
        raise HTTPException(status_code=503, detail=f"Embedding backend failed: {type(e).__name__}")
    return EmbedResponse(embeddings=out, dimension=len(out[0]), model=EMBED_MODEL)


@app.post("/api/v1/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    # zero candidates needs no model: same shortcut as the intramind layer
    if not req.documents:
        return RerankResponse(results=[])
    # truncate, never reject: a 4xx here would kill the user's whole query upstream
    docs = req.documents[:RERANK_MAX_BATCH] if RERANK_MAX_BATCH > 0 else req.documents
    try:
        async with client() as c:
            r = await c.post(f"{RERANK_URL}/score", json={
                "model": RERANK_MODEL, "text_1": req.query, "text_2": docs,
                "truncate_prompt_tokens": RERANK_MAX_TOKENS})
            r.raise_for_status()
            scores = {d["index"]: float(d["score"]) for d in r.json()["data"]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Rerank backend failed: {type(e).__name__}")
    order = sorted(range(len(docs)), key=lambda i: -scores.get(i, 0.0))
    if req.top_k is not None:
        order = order[:max(req.top_k, 0)]
    return RerankResponse(results=[RerankResultItem(index=i, score=scores.get(i, 0.0)) for i in order])


@app.get("/health")
async def health():
    async def probe(url: str) -> bool:
        try:
            async with client() as c:
                return (await c.get(f"{url}/health", timeout=5)).status_code == 200
        except Exception:
            return False
    emb, rer = await asyncio.gather(probe(EMBED_URL), probe(RERANK_URL))
    body = {"status": "ok" if emb and rer else "degraded", "model": EMBED_MODEL, "dimension": 640,
            "embedding_backend": emb, "rerank_backend": rer}
    if not (emb and rer):
        raise HTTPException(status_code=503, detail=body)
    return body
