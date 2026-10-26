import os
import unittest
import uuid

from qdrant_client import QdrantClient

from app.org import Principal, UnitTree, place_upload, scope_for
from app.parsing import Metadata, ParsedDocument, Section
from app.parsing.models import Block
from app.search import HashEmbedder, QdrantIndex, SearchFilters, doc_vector, query_vector
from app.search.sparse import term_id, terms, tokens
from app.search.store import point_id, scope_filter

URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
KEY = os.getenv("QDRANT_API_KEY", "ChangeQdrantKey_2026")

class SparseTests(unittest.TestCase):
    def test_tokens_keep_vietnamese_syllables_and_drop_punctuation(self):
        self.assertEqual(tokens("Quân khu 3, Phòng Công binh!"), ["quân", "khu", "3", "phòng", "công", "binh"])

    def test_bigrams_give_phrase_matching(self):
        self.assertEqual(terms("công binh quân khu"), ["công", "binh", "quân", "khu", "công binh", "binh quân", "quân khu"])

    def test_term_id_is_stable_and_u32(self):
        self.assertEqual(term_id("quân khu"), term_id("quân khu"))
        self.assertTrue(0 <= term_id("quân khu") < 2 ** 32)

    def test_nfc_and_nfd_spellings_match(self):
        import unicodedata
        word = "Quân khu"
        self.assertEqual(doc_vector(unicodedata.normalize("NFD", word)), doc_vector(unicodedata.normalize("NFC", word)))

    def test_bm25_weight_saturates_and_penalises_length(self):
        _, short = doc_vector("rada " * 1)
        _, repeated = doc_vector("rada " * 5)
        self.assertGreater(repeated[0], short[0])
        self.assertLess(repeated[0], 5 * short[0])  # saturation: five mentions are not worth five times one
        _, long_doc = doc_vector("rada " + "x " * 600)
        _, one = doc_vector("rada " + "x " * 20)
        self.assertLess(long_doc[0], one[0])  # the same single mention weighs less in a longer chunk

    def test_query_vector_is_binary_over_unique_terms(self):
        idx, val = query_vector("công binh công binh")
        self.assertEqual(set(val), {1.0})
        self.assertEqual(len(idx), len(set(idx)))

    def test_hash_embedder_is_deterministic_and_unit_length(self):
        e = HashEmbedder(64)
        a, b = e.embed_query("công binh"), e.embed_documents(["công binh"])[0]
        self.assertEqual(a, b)
        self.assertAlmostEqual(sum(x * x for x in a), 1.0, places=6)

    def test_point_ids_are_stable(self):
        self.assertEqual(point_id("d1", 0), point_id("d1", 0))
        self.assertNotEqual(point_id("d1", 0), point_id("d1", 1))

class ScopeFilterTests(unittest.TestCase):
    def test_filter_requires_unit_in_path_and_allowed_level(self):
        tree = UnitTree.load()
        flt = scope_filter(scope_for(tree, Principal("btm.cong_binh", "staff")))
        keys = {c.key: c.match for c in flt.must}
        self.assertEqual(keys["unit_path"].value, "btm.cong_binh")
        self.assertEqual(keys["level"].any, ["thuong"])
        commander = scope_filter(scope_for(tree, Principal("btm", "commander")))
        self.assertEqual({c.key: c.match for c in commander.must}["level"].any, ["mat", "thuong"])

def make_doc(title: str, body: str, doc_type="Báo cáo") -> ParsedDocument:
    root = Section("root", children=[Section("roman", "I", "I. NỘI DUNG", 1, [Block("para", body, 2)])])
    return ParsedDocument("x.docx", "docx", Metadata(doc_type=doc_type, number="7", symbol="BC-QK3", date="2026-05-04",
                                                     issuing_agency="BỘ THAM MƯU", title=title), root)

def reachable() -> bool:
    try:
        QdrantClient(url=URL, api_key=KEY, timeout=3).get_collections()
        return True
    except Exception:
        return False

@unittest.skipUnless(reachable(), f"Qdrant không chạy ở {URL}")
class QdrantHybridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = UnitTree.load()
        cls.client = QdrantClient(url=URL, api_key=KEY)
        cls.name = f"test_{uuid.uuid4().hex[:10]}"
        cls.index = QdrantIndex(cls.client, HashEmbedder(128), cls.name)
        cls.index.ensure_collection()
        cb, qb = Principal("btm.cong_binh", "staff"), Principal("btm.quan_bao", "staff")
        cls.docs = {
            "A": (make_doc("Về công sự trận địa", "Xây dựng công sự trận địa pháo binh theo mã hiệu ZX-4471 tại khu vực phía Bắc."), place_upload(cls.tree, cb)),
            "B": (make_doc("Về trinh sát", "Xây dựng công sự trận địa quan sát cho đài trinh sát, mã hiệu ZX-9902."), place_upload(cls.tree, qb)),
            "C": (make_doc("Kế hoạch hành quân", "Công sự trận địa hành quân theo mã hiệu ZX-5530 phương án bí mật.", "Kế hoạch"),
                  place_upload(cls.tree, cb, declared_secret=True)),
        }
        for doc_id, (doc, placement) in cls.docs.items():
            cls.index.index_document(doc_id, doc, placement)

    @classmethod
    def tearDownClass(cls):
        cls.client.delete_collection(cls.name)

    def ids(self, who, query, **kw):
        return {h.doc_id for h in self.index.search(query, scope_for(self.tree, who), k=20, **kw)}

    def test_staff_sees_only_own_unit_and_not_secret(self):
        got = self.ids(Principal("btm.cong_binh", "staff"), "công sự trận địa")
        self.assertEqual(got, {"A"})  # B is a sibling's, C is secret

    def test_commander_of_the_unit_also_sees_secret(self):
        self.assertEqual(self.ids(Principal("btm.cong_binh", "commander"), "công sự trận địa"), {"A", "C"})

    def test_parent_agency_sees_children_but_still_no_secret_for_staff(self):
        self.assertEqual(self.ids(Principal("btm", "staff"), "công sự trận địa"), {"A", "B"})
        self.assertEqual(self.ids(Principal("btm", "commander"), "công sự trận địa"), {"A", "B", "C"})

    def test_an_exact_match_on_a_forbidden_document_still_returns_nothing(self):
        for code, doc in (("ZX-9902", "B"), ("ZX-5530", "C")):
            hits = self.index.search(code, scope_for(self.tree, Principal("btm.cong_binh", "staff")), k=20)
            self.assertNotIn(doc, {h.doc_id for h in hits}, code)

    def test_unrelated_unit_sees_nothing(self):
        self.assertEqual(self.ids(Principal("hckt.quan_y", "commander"), "công sự trận địa"), set())

    def test_sparse_leg_finds_a_rare_code_that_dense_hashing_cannot_rank(self):
        hits = self.index.search("ZX-4471", scope_for(self.tree, Principal("btm", "commander")), k=5)
        self.assertEqual(hits[0].doc_id, "A")

    def test_extra_filters_narrow_but_never_widen(self):
        who = Principal("btm.cong_binh", "staff")
        self.assertEqual(self.ids(who, "công sự", filters=SearchFilters(doc_types=["Kế hoạch"])), set())  # C is the only Kế hoạch
        self.assertEqual(self.ids(Principal("btm", "commander"), "công sự", filters=SearchFilters(doc_types=["Kế hoạch"])), {"C"})
        self.assertEqual(self.ids(who, "công sự", filters=SearchFilters(doc_ids=["B"])), set())

    def test_both_fusion_modes_work(self):
        who = Principal("btm", "commander")
        for mode in ("rrf", "dbsf"):
            self.assertEqual({h.doc_id for h in self.index.search("công sự", scope_for(self.tree, who), k=10, fusion=mode)}, {"A", "B", "C"})

    def test_reindex_replaces_and_removes_stale_chunks(self):
        who, placement = Principal("btm.cong_binh", "staff"), place_upload(self.tree, Principal("btm.cong_binh", "staff"))
        long = make_doc("Dài", " ".join(f"đoạn{i}. " + "từ " * 60 for i in range(12)))
        n1 = self.index.index_document("R", long, placement)
        self.assertGreater(n1, 2)
        self.assertEqual(self.index.count("R"), n1)
        short = make_doc("Ngắn", "chỉ còn một đoạn ngắn")
        n2 = self.index.index_document("R", short, placement)
        self.assertEqual(self.index.count("R"), n2)
        self.assertLess(n2, n1)
        self.index.delete_document("R")
        self.assertEqual(self.index.count("R"), 0)

    def test_hit_carries_citation_data(self):
        h = self.index.search("ZX-4471", scope_for(self.tree, Principal("btm", "commander")), k=1)[0]
        self.assertEqual((h.doc_id, h.chunk_id.split("#")[0]), ("A", "A"))
        self.assertIn("Báo cáo 7/BC-QK3 (4/5/2026)", h.context)
        self.assertEqual(h.payload["unit_path"], ["btl", "btm", "btm.cong_binh"])

if __name__ == "__main__":
    unittest.main()
