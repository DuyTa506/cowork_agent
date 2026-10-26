import shutil
import tempfile
import unittest
from pathlib import Path

from app.parsing import ChunkConfig, Metadata, ParsedDocument, Section, chunk_document, parse_file
from app.parsing.models import Block
from test_parsing import build_decision

CFG = ChunkConfig(target=60, max=100, min=20)

def words(n: int, tag: str = "w") -> str:
    return " ".join(f"{tag}{i}" for i in range(n))

def doc_of(root: Section, **meta) -> ParsedDocument:
    return ParsedDocument("x.docx", "docx", Metadata(doc_type="Kế hoạch", number="7", symbol="KH-QK3", date="2026-05-04",
                                                     issuing_agency="QUÂN KHU 3", title="Về việc A", **meta), root)

def dieu(n: int, body_words: int) -> Section:
    return Section("dieu", f"Điều {n}", f"Điều {n}. Tên điều {n}", n * 10, [Block("para", words(body_words, f"d{n}_"), n * 10 + 1)])

class ChunkerTests(unittest.TestCase):
    def test_meta_card_comes_first_and_names_the_signer(self):
        doc = doc_of(Section("root", blocks=[Block("para", words(30), 1)]), signer_role="TƯ LỆNH", signer_name="Trung tướng An",
                     distribution=["Như trên", "Lưu: VT"])
        chunks = chunk_document(doc, "d1", CFG)
        self.assertEqual(chunks[0].part, "meta")
        self.assertIn("Người ký: TƯ LỆNH Trung tướng An", chunks[0].text)
        self.assertIn("Nơi nhận: Như trên; Lưu: VT", chunks[0].text)
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[1].id, "d1#1")

    def test_sections_big_enough_stay_separate_even_when_they_would_fit_together(self):
        root = Section("root", children=[dieu(1, 25), dieu(2, 25)])  # 29 + 29 words < target 60, each >= min 20
        body = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertEqual(len(body), 2)
        self.assertTrue(body[0].text.startswith("Điều 1."))
        self.assertTrue(body[1].text.startswith("Điều 2."))

    def test_tiny_sections_are_merged(self):
        root = Section("root", children=[dieu(i, 4) for i in range(1, 9)])
        body = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertLess(len(body), 8)
        self.assertEqual(sum(c.text.count("Điều ") for c in body), 8)  # every heading survives the merge

    def test_long_section_is_split_with_breadcrumb_and_nothing_lost(self):
        paragraphs = [Block("para", words(45, f"p{i}_") + ".", 100 + i) for i in range(8)]
        root = Section("root", children=[Section("dieu", "Điều 1", "Điều 1. Rất dài", 99, paragraphs)])
        chunks = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertGreater(len(chunks), 2)
        for c in chunks:
            self.assertLessEqual(c.words, CFG.max)
            self.assertEqual(c.path, ["Điều 1. Rất dài"])
        joined = " ".join(c.text for c in chunks)
        for i in range(8):
            self.assertIn(f"p{i}_0", joined)
        self.assertEqual(sum(c.words for c in chunks), 8 * 45 + 4)  # the heading's 4 words + all paragraph words

    def test_one_endless_sentence_is_cut_by_words(self):
        root = Section("root", children=[Section("number", "1", "1. " + words(300), 5)])
        chunks = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertTrue(all(c.words <= CFG.max for c in chunks))
        self.assertEqual(sum(c.words for c in chunks), 301)

    def test_table_is_split_by_rows_and_repeats_a_short_header(self):
        rows = ["STT | Họ tên | Chức vụ"] + [f"{i} | {words(8, 'n')} | {words(8, 'c')}" for i in range(30)]
        root = Section("root", children=[Section("roman", "I", "I. DANH SÁCH", 1, [Block("table", "\n".join(rows), 2)])])
        chunks = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertGreater(len(chunks), 3)
        tables = [c for c in chunks if "STT | Họ tên" in c.text]
        self.assertEqual(len(tables), len(chunks))  # header row at the top of every piece

    def test_long_first_table_row_is_not_repeated(self):
        rows = [words(50, "x") + " | a"] + [f"{i} | {words(10, 'r')}" for i in range(20)]
        root = Section("root", children=[Section("roman", "I", "I. BẢNG", 1, [Block("table", "\n".join(rows), 2)])])
        chunks = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"]
        self.assertEqual(sum(c.text.count("x0 ") for c in chunks), 1)

    def test_embed_text_has_context_and_breadcrumb(self):
        root = Section("root", children=[dieu(3, 40)])
        c = [c for c in chunk_document(doc_of(root), "d", CFG) if c.part == "body"][0]
        self.assertTrue(c.context.startswith("Kế hoạch 7/KH-QK3 (4/5/2026) - QUÂN KHU 3 - Về việc A"))
        self.assertTrue(c.embed_text.startswith(c.context))
        self.assertIn("Điều 3. Tên điều 3", c.embed_text.split("\n")[1])

class ChunkFromFileTests(unittest.TestCase):
    def test_annex_after_signature_is_chunked(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            build_decision(tmp / "qd.docx", annex=True)
            chunks = chunk_document(parse_file(tmp / "qd.docx"), "qd")
            text = "\n".join(c.text for c in chunks if c.part != "meta")
            self.assertIn("Trần Văn C", text)
            self.assertNotIn("Nơi nhận", text)
            self.assertIn("Trung tướng Nguyễn Văn An", chunks[0].text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
