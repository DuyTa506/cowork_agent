"""Reranker and intramind-embedder wire protocols, and the rerank stage of retrieval (no model server, no Qdrant)."""
import json
import unittest

import httpx

from app.rag.tools import retrieve
from app.search import make_embedder, make_reranker
from app.search.embedders import IntramindEmbedder
from app.search.rerank import HttpReranker
from app.search.store import Hit


def _serve(handler):
    return httpx.MockTransport(handler)


def _reranker(protocol, handler) -> HttpReranker:
    r = HttpReranker("http://serving", "m", protocol)
    r._client = httpx.Client(base_url="http://serving", transport=_serve(handler))
    return r


class ProtocolTests(unittest.TestCase):
    def test_intramind_rerank_uses_its_path_and_maps_scores_back_to_input_order(self):
        seen = {}

        def handler(request):
            seen.update(path=request.url.path, body=json.loads(request.content))
            return httpx.Response(200, json={"results": [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.1}]})

        scores = _reranker("intramind", handler).rerank("q", ["a", "b", "c"])
        self.assertEqual(seen["path"], "/api/v1/rerank")
        self.assertEqual(seen["body"], {"query": "q", "documents": ["a", "b", "c"], "top_k": 3})
        self.assertEqual(scores, [0.1, 0.0, 0.9])  # a document the server left out scores zero

    def test_cohere_and_tei_keep_the_plain_rerank_path(self):
        paths = []

        def handler(request):
            paths.append(request.url.path)
            return httpx.Response(200, json=[{"index": 0, "score": 1.0}] if "texts" in json.loads(request.content) else
                                  {"results": [{"index": 0, "relevance_score": 1.0}]})

        for protocol in ("cohere", "tei"):
            self.assertEqual(_reranker(protocol, handler).rerank("q", ["a"]), [1.0])
        self.assertEqual(paths, ["/rerank", "/rerank"])

    def test_intramind_embedder_sends_input_type_and_checks_the_dimension(self):
        calls = []

        def handler(request):
            body = json.loads(request.content)
            calls.append((request.url.path, body["input_type"], len(body["texts"])))
            return httpx.Response(200, json={"embeddings": [[0.0, 1.0]] * len(body["texts"]), "dimension": 2, "model": "x"})

        e = IntramindEmbedder("http://serving", 2, batch_size=2)
        e._client = httpx.Client(base_url="http://serving", transport=_serve(handler))
        self.assertEqual(len(e.embed_documents(["a", "b", "c"])), 3)
        self.assertEqual(e.embed_query("q"), [0.0, 1.0])
        self.assertEqual(calls, [("/api/v1/embed", "document", 2), ("/api/v1/embed", "document", 1), ("/api/v1/embed", "query", 1)])
        e.dim = 3
        with self.assertRaises(ValueError):
            e.embed_query("q")

    def test_factory_builds_both_from_settings(self):
        self.assertIsInstance(make_embedder({"provider": "intramind", "base_url": "http://s", "dim": 640}), IntramindEmbedder)
        self.assertIsNone(make_reranker({"enabled": False, "base_url": "http://s"}))
        self.assertEqual(make_reranker({"enabled": True, "base_url": "http://s", "protocol": "intramind"}).protocol, "intramind")


class FakeIndex:
    """Returns the same chunks for any query and records how many were asked for."""

    def __init__(self, texts):
        self.hits = [Hit(f"d#{i}", "d", 1.0 - i / 10, t, "ctx", [], {}) for i, t in enumerate(texts)]
        self.asked = None

    def search(self, query, scope, k, filters=None, mode="hybrid"):
        self.asked = k
        return self.hits[:k]


class KeywordReranker:
    def rerank(self, query, documents):
        return [float(query in d) for d in documents]


class BrokenReranker:
    def rerank(self, query, documents):
        raise httpx.ConnectError("down")


class RetrieveTests(unittest.TestCase):
    TEXTS = ["x", "y", "z", "the answer", "w"]

    def test_without_a_reranker_the_first_stage_decides(self):
        index = FakeIndex(self.TEXTS)
        self.assertEqual([h.chunk_id for h in retrieve(index, None, "answer", 2, mode="hybrid")], ["d#0", "d#1"])
        self.assertEqual(index.asked, 2)

    def test_the_reranker_pulls_a_low_ranked_chunk_to_the_top_and_more_candidates_are_fetched(self):
        index = FakeIndex(self.TEXTS)
        hits = retrieve(index, None, "answer", 2, mode="hybrid", reranker=KeywordReranker(), candidates=5)
        self.assertEqual(index.asked, 5)
        self.assertEqual(hits[0].chunk_id, "d#3")
        self.assertEqual(len(hits), 2)

    def test_candidates_never_drop_below_top_k(self):
        index = FakeIndex(self.TEXTS)
        retrieve(index, None, "answer", 5, mode="hybrid", reranker=KeywordReranker(), candidates=3)
        self.assertEqual(index.asked, 5)

    def test_a_failing_reranker_keeps_the_first_stage_order(self):
        hits = retrieve(FakeIndex(self.TEXTS), None, "answer", 3, mode="hybrid", reranker=BrokenReranker(), candidates=5)
        self.assertEqual([h.chunk_id for h in hits], ["d#0", "d#1", "d#2"])


if __name__ == "__main__":
    unittest.main()
