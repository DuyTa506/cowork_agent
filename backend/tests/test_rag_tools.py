import asyncio
import json
import os
import sys
import time
import unittest
import uuid

import jwt
from mcp import Client, StdioServerParameters
from qdrant_client import QdrantClient

from app.org import Principal, UnitTree, place_upload, scope_for
from app.parsing import Metadata, ParsedDocument, Section
from app.parsing.models import Block
from app.rag import identity
from app.rag.tools import NOT_FOUND, RagTools
from app.search import HashEmbedder, QdrantIndex

URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
KEY = os.getenv("QDRANT_API_KEY", "ChangeQdrantKey_2026")
SECRET = "test-secret-" + "x" * 40
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def doc(title, body, doc_type="Báo cáo", date="2026-05-04", number="7"):
    root = Section("root", children=[Section("roman", "I", "I. NỘI DUNG", 1, [Block("para", body, 2)])])
    return ParsedDocument("x.docx", "docx", Metadata(doc_type=doc_type, number=number, symbol="BC-QK3", date=date,
                                                     issuing_agency="BỘ THAM MƯU", title=title), root)

def reachable():
    try:
        QdrantClient(url=URL, api_key=KEY, timeout=3).get_collections()
        return True
    except Exception:
        return False

class IdentityTests(unittest.TestCase):
    def test_roundtrip(self):
        who = Principal("btm.cong_binh", "commander")
        self.assertEqual(identity.verify(identity.issue(who, SECRET), SECRET), who)

    def test_rejects_tampering_expiry_wrong_secret_and_missing(self):
        who = Principal("btm.cong_binh", "staff")
        good = identity.issue(who, SECRET)
        with self.assertRaises(identity.IdentityError):
            identity.verify(good, "another-secret-" + "y" * 40)
        with self.assertRaises(identity.IdentityError):
            identity.verify(identity.issue(who, SECRET, ttl_seconds=-5), SECRET)
        forged = jwt.encode({"unit": "btl", "role": "commander", "exp": int(time.time()) + 60, "aud": "qk3-tools"}, "guess", algorithm="HS256")
        with self.assertRaises(identity.IdentityError):
            identity.verify(forged, SECRET)
        with self.assertRaises(identity.IdentityError):
            identity.verify(jwt.encode({"unit": "btl", "exp": int(time.time()) + 60, "aud": "qk3-tools"}, SECRET, algorithm="HS256"), SECRET)  # no role
        os.environ.pop(identity.ENV_TOKEN, None)
        with self.assertRaises(identity.IdentityError):
            identity.from_environment(SECRET)

@unittest.skipUnless(reachable(), f"Qdrant không chạy ở {URL}")
class ToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = UnitTree.load()
        cls.client = QdrantClient(url=URL, api_key=KEY)
        cls.name = f"test_{uuid.uuid4().hex[:10]}"
        cls.index = QdrantIndex(cls.client, HashEmbedder(128), cls.name)
        cls.index.ensure_collection()
        cb, qb = Principal("btm.cong_binh", "staff"), Principal("btm.quan_bao", "staff")
        long_body = " ".join(f"Đoạn {i}: " + "nội dung kế hoạch huấn luyện " * 20 + "." for i in range(12))
        cls.docs = {
            "A": (doc("Công sự trận địa", "Xây dựng công sự trận địa pháo binh mã ZX-4471.", date="2026-05-04"), place_upload(cls.tree, cb)),
            "OLD": (doc("Công sự năm trước", "Báo cáo công sự trận địa năm 2024.", date="2024-03-01", number="3"), place_upload(cls.tree, cb)),
            "KH": (doc("Kế hoạch huấn luyện", long_body, "Kế hoạch", "2026-06-10", "9"), place_upload(cls.tree, cb)),
            "B": (doc("Trinh sát", "Công sự quan sát mã ZX-9902 của đài trinh sát.", date="2026-05-20"), place_upload(cls.tree, qb)),
            "C": (doc("Hành quân", "Công sự hành quân mã ZX-5530 phương án bí mật.", date="2026-05-21"),
                  place_upload(cls.tree, cb, declared_secret=True)),
        }
        for doc_id, (d, placement) in cls.docs.items():
            cls.index.index_document(doc_id, d, placement)

    @classmethod
    def tearDownClass(cls):
        cls.client.delete_collection(cls.name)

    def tools(self, unit, role):
        return RagTools(self.index, scope_for(self.tree, Principal(unit, role)))

    def test_search_returns_citable_bounded_snippets(self):
        res = self.tools("btm.cong_binh", "staff").search_documents("công sự trận địa", top_k=5)
        self.assertTrue(res)
        for r in res:
            self.assertRegex(r["cite"], r"^[A-Z]+#\d+$")
            self.assertLessEqual(len(r["text"]), 905)
            self.assertIn("doc", r)
        self.assertEqual({r["doc_id"] for r in res}, {"A", "OLD", "KH"})  # not B (sibling) nor C (secret)

    def test_search_filters(self):
        t = self.tools("btm", "commander")
        for q in ("công sự", "kế hoạch huấn luyện"):  # the filter leaves only the one Kế hoạch, whatever the query
            self.assertEqual({r["doc_id"] for r in t.search_documents(q, doc_type="Kế hoạch")}, {"KH"}, q)
        self.assertEqual({r["doc_id"] for r in t.search_documents("công sự", doc_type="Báo cáo", top_k=20)}, {"A", "OLD", "B", "C"})
        recent = {r["doc_id"] for r in t.search_documents("công sự trận địa", date_from="2026-01-01")}
        self.assertNotIn("OLD", recent)

    def test_keyword_mode_finds_exact_codes(self):
        t = self.tools("btm", "commander")
        res = t.search_documents("ZX-4471", mode="keyword", top_k=3)
        self.assertEqual(res[0]["doc_id"], "A")
        self.assertEqual(t.search_documents("từ-không-có-trong-kho-xyz", mode="keyword"), [])

    def test_semantic_mode_returns_ranked_chunks(self):
        res = self.tools("btm", "commander").search_documents("công sự trận địa", mode="semantic", top_k=4)
        self.assertEqual(len(res), 4)
        self.assertEqual([r["score"] for r in res], sorted((r["score"] for r in res), reverse=True))

    def test_every_mode_stays_inside_the_scope(self):
        staff = self.tools("btm.cong_binh", "staff")
        for mode in ("keyword", "semantic", "hybrid"):
            for q in ("ZX-9902", "ZX-5530 phương án bí mật", "công sự"):  # B is a sibling unit's, C is secret
                ids = {r["doc_id"] for r in staff.search_documents(q, mode=mode, top_k=20)}
                self.assertFalse(ids & {"B", "C"}, (mode, q, ids))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tools("btm", "commander").search_documents("công sự", mode="fuzzy")

    def test_metadata_filters(self):
        t = self.tools("btm", "commander")
        ids = lambda **kw: {r["doc_id"] for r in t.search_documents("công sự", top_k=20, **kw)}  # noqa: E731
        self.assertEqual(ids(number="3"), {"OLD"})
        self.assertEqual(ids(symbol="BC-QK3"), {"A", "OLD", "KH", "B", "C"})
        self.assertEqual(ids(symbol="KH-QK3"), set())
        self.assertEqual(ids(issuing_agency="bo tham muu"), {"A", "OLD", "KH", "B", "C"})  # accents and case do not matter
        self.assertEqual(ids(issuing_agency="tham mưu bộ"), {"A", "OLD", "KH", "B", "C"})  # order does not matter
        self.assertEqual(ids(issuing_agency="hậu cần"), set())
        self.assertEqual(ids(title="cong su nam truoc"), {"OLD"})
        self.assertEqual(ids(date_from="2026-05-01", date_to="2026-05-31"), {"A", "B", "C"})

    def test_list_documents_by_metadata_only(self):
        t = self.tools("btm", "commander")
        self.assertEqual([r["doc_id"] for r in t.list_documents(title="trinh sat")], ["B"])
        self.assertEqual([r["doc_id"] for r in t.list_documents(number="9")], ["KH"])
        self.assertEqual([r["doc_id"] for r in self.tools("btm.cong_binh", "staff").list_documents(title="trinh sat")], [])

    def test_read_document_pages_and_covers_everything(self):
        t = self.tools("btm.cong_binh", "staff")
        first = t.read_document("KH")
        self.assertEqual(first["offset"], 0)
        self.assertLessEqual(len(first["text"]), 6000)
        self.assertIsNotNone(first["next_offset"])
        text, page = first["text"], first
        while page["next_offset"] is not None:
            page = t.read_document("KH", offset=page["next_offset"])
            text += page["text"]
        self.assertEqual(len(text), first["total_chars"])
        self.assertIn("Đoạn 11:", text)

    def test_forbidden_and_missing_documents_look_identical(self):
        t = self.tools("btm.cong_binh", "staff")
        for doc_id in ("B", "C", "does-not-exist"):  # sibling's, secret, nonexistent
            self.assertEqual(t.read_document(doc_id), {"error": NOT_FOUND}, doc_id)
        self.assertNotEqual(self.tools("btm.cong_binh", "commander").read_document("C").get("error"), NOT_FOUND)

    def test_list_documents_newest_first_with_filters_and_scope(self):
        got = self.tools("btm", "commander").list_documents()
        dates = [r["ngay"] for r in got]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual({r["doc_id"] for r in got}, {"A", "OLD", "KH", "B", "C"})
        staff = self.tools("btm.cong_binh", "staff").list_documents()
        self.assertEqual({r["doc_id"] for r in staff}, {"A", "OLD", "KH"})
        self.assertEqual([r["doc_id"] for r in self.tools("btm", "commander").list_documents(doc_type="Kế hoạch")], ["KH"])
        self.assertEqual([r["doc_id"] for r in self.tools("btm", "commander").list_documents(date_to="2025-01-01")], ["OLD"])

    def test_top_k_is_clamped(self):
        self.assertLessEqual(len(self.tools("btm", "commander").search_documents("công sự", top_k=10_000)), 20)

@unittest.skipUnless(reachable(), f"Qdrant không chạy ở {URL}")
class McpServerTests(unittest.TestCase):
    """Starts the real server process over stdio and talks to it like the agent harness does."""

    @classmethod
    def setUpClass(cls):
        cls.tree = UnitTree.load()
        cls.client = QdrantClient(url=URL, api_key=KEY)
        cls.name = f"test_{uuid.uuid4().hex[:10]}"
        cls.index = QdrantIndex(cls.client, HashEmbedder(128), cls.name)
        cls.index.ensure_collection()
        cb, qb = Principal("btm.cong_binh", "staff"), Principal("btm.quan_bao", "staff")
        cls.index.index_document("A", doc("Công sự", "Xây dựng công sự trận địa pháo binh mã ZX-4471."), place_upload(cls.tree, cb))
        cls.index.index_document("B", doc("Trinh sát", "Công sự quan sát mã ZX-9902."), place_upload(cls.tree, qb))

    @classmethod
    def tearDownClass(cls):
        cls.client.delete_collection(cls.name)

    def params(self, token):
        env = {"QK3_EMBEDDER": "hash", "QK3_EMBEDDER_DIM": "128", "QDRANT_URL": URL, "QDRANT_API_KEY": KEY, "QDRANT_COLLECTION": self.name,
               "JWT_SECRET": SECRET, "PYTHONPATH": BACKEND}
        if token:
            env[identity.ENV_TOKEN] = token
        return StdioServerParameters(command=sys.executable, args=["-m", "app.rag.mcp_server"], env=env, cwd=BACKEND)

    def call(self, who, name, args):
        async def run():
            async with Client(self.params(identity.issue(who, SECRET))) as c:
                tools = {t.name for t in (await c.list_tools()).tools}
                res = await c.call_tool(name, args)
                return tools, res
        return asyncio.run(run())

    @staticmethod
    def payload(res):
        sc = getattr(res, "structured_content", None)
        if sc:
            return sc.get("result", sc)
        return json.loads(res.content[0].text)

    def test_lists_the_three_tools(self):
        tools, _ = self.call(Principal("btm.cong_binh", "staff"), "list_documents", {})
        self.assertEqual(tools, {"search_documents", "read_document", "list_documents"})

    def test_search_runs_under_the_tokens_scope(self):
        _, res = self.call(Principal("btm.cong_binh", "staff"), "search_documents", {"query": "công sự mã ZX-9902"})
        self.assertEqual({r["doc_id"] for r in self.payload(res)}, {"A"})  # B belongs to a sibling unit
        _, res = self.call(Principal("btm", "staff"), "search_documents", {"query": "công sự"})
        self.assertEqual({r["doc_id"] for r in self.payload(res)}, {"A", "B"})

    def test_a_model_cannot_ask_for_more_than_its_token_allows(self):
        # there is no identity parameter on any tool, and a forbidden document id is refused
        _, res = self.call(Principal("btm.cong_binh", "staff"), "read_document", {"doc_id": "B"})
        self.assertEqual(self.payload(res), {"error": NOT_FOUND})

    def test_refuses_to_start_without_or_with_a_bad_token(self):
        """Run the server directly so the *reason* for refusing is checked, not just that it died."""
        import subprocess
        forged = identity.issue(Principal("btl", "commander"), "other-secret-" + "z" * 40)
        for token, reason in (("", "Thiếu QK3_SCOPE_TOKEN"), ("not-a-token", "Token không hợp lệ"), (forged, "Token không hợp lệ")):
            p = self.params(token)
            env = {**os.environ, **p.env}
            if not token:
                env.pop(identity.ENV_TOKEN, None)
            r = subprocess.run([sys.executable, "-m", "app.rag.mcp_server"], env=env, cwd=BACKEND, capture_output=True, text=True,
                               timeout=60, stdin=subprocess.DEVNULL)
            self.assertNotEqual(r.returncode, 0, token)
            self.assertIn(reason, r.stderr, token)

if __name__ == "__main__":
    unittest.main()
