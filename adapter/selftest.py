"""Offline self-test of the adapter with fake vLLM backends (no GPU, no model). Run: scripts/selftest.sh"""
import asyncio, json, sys
import httpx

sys.path.insert(0, "/adapter")
import app as A


def fake_backend(request: httpx.Request) -> httpx.Response:
    p, body = request.url.path, (json.loads(request.content) if request.content else {})
    if p == "/health":
        return httpx.Response(200, json={})
    if p == "/v1/embeddings":
        FAKE.setdefault("embed_inputs", []).append(body["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [3.0, 4.0, 0.0] if "Query" in t else [0.0, 0.0, 2.0]}
                                                   for i, t in reversed(list(enumerate(body["input"])))]})
    if p == "/score":
        return httpx.Response(200, json={"data": [{"index": i, "score": 1.0 / (1 + len(d))} for i, d in enumerate(body["text_2"])]})
    return httpx.Response(404)


FAKE: dict = {}


async def main():
    A._transport = httpx.MockTransport(fake_backend)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=A.app), base_url="http://t") as c:
        r = await c.post("/api/v1/embed", json={"texts": ["a", "b"]})
        assert r.status_code == 200 and set(r.json()) == {"embeddings", "dimension", "model"}, r.text
        assert r.json()["dimension"] == 3 and r.json()["embeddings"][0] == [0.0, 0.0, 1.0], r.json()  # unit norm, order kept
        r = await c.post("/api/v1/embed", json={"texts": ["x"], "input_type": "query"})
        assert FAKE["embed_inputs"][-1][0].startswith("Instruct: Given a web search query"), FAKE["embed_inputs"][-1]
        assert r.json()["embeddings"][0] == [0.6, 0.8, 0.0], r.json()  # the query path got the prefix, and was normalised
        r = await c.post("/api/v1/embed", json={"texts": [str(i) for i in range(130)]})
        assert len(r.json()["embeddings"]) == 130 and len(FAKE["embed_inputs"]) >= 4  # split into batches of 64
        assert (await c.post("/api/v1/embed", json={"texts": []})).status_code == 422
        r = await c.post("/api/v1/rerank", json={"query": "q", "documents": []})
        assert r.status_code == 200 and r.json() == {"results": []}
        r = await c.post("/api/v1/rerank", json={"query": "q", "documents": ["longer text", "x", "mid size"], "top_k": 2})
        assert [i["index"] for i in r.json()["results"]] == [1, 2], r.json()
        r = await c.post("/api/v1/rerank", json={"query": "q", "documents": ["d"] * 250})
        assert len(r.json()["results"]) == A.RERANK_MAX_BATCH  # truncated, not rejected
        r = await c.get("/health"); assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    A._transport = httpx.MockTransport(lambda req: httpx.Response(500))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=A.app), base_url="http://t") as c:
        assert (await c.post("/api/v1/embed", json={"texts": ["a"]})).status_code == 503
        assert (await c.post("/api/v1/rerank", json={"query": "q", "documents": ["a"]})).status_code == 503
        assert (await c.get("/health")).status_code == 503
    print("adapter selftest OK")

asyncio.run(main())
