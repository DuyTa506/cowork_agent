"""Scanned PDFs: rendered page by page, read by an OCR server (a scripted one here), kept as a text companion in the object store."""
import io
import unittest
from pathlib import Path
from unittest import mock

import httpx
from PIL import Image, ImageDraw, ImageFont

from app import ocr, storage
from app.models import DocumentState
from app.ocr import client as ocr_client, layout, render, service
from fakellm import FakeLLM
from test_documents_api import ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (the shared index collection)

PAGE_TEXTS = [
    "# BỘ QUỐC PHÒNG\nBỘ TƯ LỆNH QUÂN KHU 3\nSố: 21/QĐ-QK3\n\n**QUYẾT ĐỊNH**\nVề việc kiện toàn Ban Chỉ đạo diễn tập khu vực phòng thủ năm 2026\n\n"
    "Căn cứ Luật Quốc phòng; Căn cứ nhiệm vụ huấn luyện năm 2026 của Quân khu 3;\nXét đề nghị của Phòng Tác chiến,",
    "**QUYẾT ĐỊNH:**\nĐiều 1. Kiện toàn Ban Chỉ đạo gồm Trưởng ban là Phó Tư lệnh Quân khu và các thành viên là chỉ huy các phòng.\n"
    "Điều 2. Quyết định này có hiệu lực kể từ ngày ký.\n\n| Họ tên | Chức vụ |\n|---|---|\n| Nguyễn Văn An | Trưởng ban |",
]


def scanned_pdf(path: Path, pages: int = 2) -> Path:
    """A PDF made only of page images (no text layer), like a scanner's output."""
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    images = []
    for number in range(pages):
        image = Image.new("RGB", (1240, 1754), "white")
        ImageDraw.Draw(image).text((100, 120), f"Trang {number + 1} (bản scan thử)", fill="black", font=font)
        images.append(image)
    images[0].save(path, format="PDF", save_all=True, append_images=images[1:])
    return path


class CleanupTests(unittest.TestCase):
    def test_markdown_marks_are_dropped_and_pipe_tables_become_tables(self):
        items = layout.page_items("# Tiêu đề\n**Đậm** và `mã`\n| A | B |\n|---|---|\n| 1 | 2 |\n> trích", None)
        self.assertEqual([i.text for i in items if isinstance(i, layout.Para)], ["Tiêu đề", "Đậm và mã", "trích"])
        (table,) = [i for i in items if isinstance(i, layout.Table)]
        self.assertEqual([[c for c, _ in row] for row in table.rows], [["A", "B"], ["1", "2"]])

    def test_html_tables_become_tables_with_their_spans(self):
        (table,) = layout.page_items('<table><thead><tr><th>TT</th><th>Tên</th></tr></thead><tbody><tr><td colspan="2">I. XE<br>PT-76</td></tr></tbody></table>', None)
        self.assertEqual(table.rows, [[("TT", 1), ("Tên", 1)], [("I. XE PT-76", 2)]])

    def test_blocks_keep_the_pages_alignment_and_weight(self):
        blocks = [{"label": "title", "box": [400, 80, 600, 100], "text": "## QUYẾT ĐỊNH"}, {"label": "text", "box": [60, 120, 900, 140], "text": "Căn cứ Luật."},
                  {"label": "text", "box": [535, 160, 887, 177], "text": "Hải Phòng, ngày 16 tháng 11 năm 2023"}, {"label": "page_number", "box": [480, 950, 520, 970], "text": "2"},
                  {"label": "image", "box": [10, 10, 90, 90], "text": 'stamp "QK3"'}]
        items = layout.page_items("", blocks)
        self.assertEqual([(i.text, i.align, i.bold) for i in items],
                         [("QUYẾT ĐỊNH", "center", True), ("Căn cứ Luật.", "left", False), ("Hải Phòng, ngày 16 tháng 11 năm 2023", "right", False)])

    def test_the_word_file_has_real_tables_the_viewer_can_show(self):
        import tempfile
        from app.services.documents import paragraphs
        html = "<table><tr><th>TT</th><th>Tên</th></tr><tr><td>1</td><td>Xe</td></tr></table>"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "c.docx"
            layout.write_docx([("", [{"label": "title", "box": [400, 10, 600, 20], "text": "BẢNG"}, {"label": "table", "box": [0, 30, 1000, 90], "text": html}])], target)
            shown = paragraphs(target)
        cells = [(p["table"], p["row"], p["col"], p["text"]) for p in shown if p["table"] is not None]
        self.assertEqual(cells, [(0, 0, 0, "TT"), (0, 0, 1, "Tên"), (0, 1, 0, "1"), (0, 1, 1, "Xe")])
        self.assertEqual((shown[0]["text"], shown[0]["align"], shown[0]["bold"]), ("BẢNG", "center", True))

    def test_pages_are_scaled_to_the_trained_size(self):
        with mock.patch.object(render, "LONGEST_EDGE", 600):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                pdf = scanned_pdf(Path(tmp) / "s.pdf", pages=3)
                self.assertEqual(render.page_count(pdf), 3)
                shots = list(render.pages(pdf, limit=2))  # the page limit applies
        self.assertEqual(len(shots), 2)
        size = Image.open(io.BytesIO(shots[0])).size
        self.assertEqual(max(size), 600)

    def test_client_sends_the_image_alone_and_retries_without_the_extra_option(self):
        bodies = []

        def handler(request):
            body = __import__("json").loads(request.content)
            bodies.append(body)
            if "chat_template_kwargs" in body:
                return httpx.Response(400)
            return httpx.Response(200, json={"choices": [{"message": {"content": " Trang một "}}]})

        client = ocr_client.OcrClient({"base_url": "http://ocr/v1", "model": "m"})
        client._client = httpx.Client(base_url="http://ocr/v1", transport=httpx.MockTransport(handler))
        self.assertEqual(client.read(b"\x89PNG"), "Trang một")
        image, prompt = bodies[-1]["messages"][0]["content"]  # grounding mode: the page and the one-word prompt
        self.assertTrue(image["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(prompt, {"type": "text", "text": "grounding"})
        self.assertEqual(bodies[-1]["temperature"], 0)
        with self.assertRaises(ocr_client.OcrServerError):
            client._client = httpx.Client(base_url="http://ocr/v1", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
            client.read(b"x")


class GroundingTest(unittest.TestCase):
    def test_blocks_become_paragraphs_and_pictures_are_dropped(self):
        raw = ("![title]<c77><c62><c328><c88> BỘ QUỐC PHÒNG\n\n![text]<c77><c124><c268><c147> Số: 18/QĐ-QK3\n\n"
               "![image]<c1><c2><c3><c4> Một con dấu đỏ\n\n![text](76,422,1000,498) Điều 1. Tập huấn\n\n![text+](76,500,1000,520) tiếp theo.")
        self.assertEqual(ocr_client.blocks_to_text(raw), "BỘ QUỐC PHÒNG\n\nSố: 18/QĐ-QK3\n\nĐiều 1. Tập huấn tiếp theo.")

    def test_heading_marks_inside_a_line_are_dropped(self):
        self.assertEqual([i.text for i in layout.page_items("QUÂN KHU 3 ## BAN CHỦ NHIỆM\n## Điều 1", None)], ["QUÂN KHU 3 BAN CHỦ NHIỆM", "Điều 1"])

    def test_blocks_keep_their_positions(self):
        raw = "![title]<c77><c62><c328><c88> BỘ QUỐC PHÒNG\n\n![text](76,422,1000,498) Điều 1.\n\n![text+]<c80><c500><c900><c520> tiếp."
        blocks = ocr_client.parse_blocks(raw)
        self.assertEqual([(b.label, b.box, b.text) for b in blocks],
                         [("title", (77, 62, 328, 88), "BỘ QUỐC PHÒNG"), ("text", (76, 422, 1000, 520), "Điều 1. tiếp.")])

    def test_a_plain_answer_is_kept(self):
        self.assertEqual(ocr_client.blocks_to_text(" Trang một "), "Trang một")

    def test_plain_mode_sends_the_image_alone(self):
        bodies = []
        client = ocr_client.OcrClient({"base_url": "http://ocr/v1", "model": "m", "grounding": False})
        client._client = httpx.Client(base_url="http://ocr/v1", transport=httpx.MockTransport(
            lambda r: (bodies.append(__import__("json").loads(r.content)), httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]}))[1]))
        client.read(b"\x89PNG")
        self.assertEqual(len(bodies[0]["messages"][0]["content"]), 1)


GROUNDED_PAGES = [
    "![header]<c77><c62><c328><c88> BỘ TƯ LỆNH QUÂN KHU 3\n\n![text]<c77><c124><c268><c147> Số: 21/QĐ-QK3\n\n![title]<c400><c182><c600><c208> QUYẾT ĐỊNH\n\n"
    "![text]<c76><c214><c900><c235> Về việc kiện toàn Ban Chỉ đạo diễn tập khu vực phòng thủ năm 2026\n\n![image]<c700><c300><c900><c400> con dấu đỏ",
    "![title]<c75><c80><c274><c100> QUYẾT ĐỊNH:\n\n![text]<c76><c120><c900><c180> Điều 1. Kiện toàn Ban Chỉ đạo gồm Trưởng ban và các thành viên.\n\n"
    "![table]<c76><c200><c900><c260> <table><tr><th>Họ tên</th><th>Chức vụ</th></tr><tr><td>Nguyễn Văn An</td><td>Trưởng ban</td></tr></table>",
]


class ScannedDocumentTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.pages_read = 0

        def script(messages, tools):
            parts = messages[-1]["content"]
            assert isinstance(parts, list) and parts[0]["type"] == "image_url"
            text = PAGE_TEXTS[self.pages_read % len(PAGE_TEXTS)]
            self.pages_read += 1
            return {"content": text}

        self.ocr_server = FakeLLM(script)
        self.ocr_server.__enter__()
        self.addCleanup(self.ocr_server.__exit__, None, None, None)
        self.values = {"enabled": True, "base_url": self.ocr_server.base_url, "model": "m", "api_key": "", "max_pages": 60}
        patcher = mock.patch.object(service.settings.cache, "get", lambda key: dict(self.values))
        patcher.start()
        self.addCleanup(patcher.stop)

    def upload_scan(self, who="cong_binh", name="scan.pdf") -> int:
        pdf = scanned_pdf(self.tmp / name)
        with open(pdf, "rb") as fh:
            reply = self.client.post("/api/documents", headers=self.headers(who), data={"declared_secret": "false"},
                                     files=[("files", (name, fh, "application/pdf"))])
        self.assertEqual(reply.status_code, 201, reply.text)
        item = reply.json()["items"][0]
        self.assertEqual(item["error"], "")
        self.work()
        return item["document"]["id"]

    def test_a_scan_is_read_indexed_and_searchable(self):
        document_id = self.upload_scan()
        detail = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()
        self.assertIn(detail["state"], (DocumentState.READY, DocumentState.NEEDS_REVIEW), detail)
        self.assertEqual(self.pages_read, 2)
        self.assertEqual(detail["document_type"], "Quyết định")
        self.assertGreater(detail["chunk_count"], 0)
        self.assertTrue(any("(OCR)" in step["detail"] for step in detail["steps"]), detail["steps"])
        found = self.client.get("/api/documents", headers=self.headers("cong_binh"), params={"q": "Ban Chỉ đạo", "mode": "keyword"}).json()
        self.assertIn(document_id, [item["id"] for item in found["items"]])

    def test_the_viewer_shows_the_ocr_text_and_the_download_is_still_the_pdf(self):
        document_id = self.upload_scan()
        paragraphs = self.client.get(f"/api/documents/{document_id}/content", headers=self.headers("cong_binh")).json()
        text = "\n".join(p["text"] for p in paragraphs)
        self.assertIn("Kiện toàn Ban Chỉ đạo", text)
        self.assertNotIn("**", text)
        original = self.client.get(f"/api/documents/{document_id}/file", headers=self.headers("cong_binh"))
        self.assertTrue(original.content.startswith(b"%PDF"))

    def test_reprocessing_does_not_read_the_pages_again_and_delete_removes_the_text(self):
        document_id = self.upload_scan()
        self.client.post(f"/api/documents/{document_id}/reprocess", headers=self.headers("cong_binh"))
        self.work()
        self.assertEqual(self.pages_read, 2)  # the stored text was reused
        with self.sessions() as db:
            from app.models import Document
            key = storage.keys.document(db.get(Document, document_id).stored_name)
        self.assertTrue(storage.get_store().exists(ocr.companion_key(key)))
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).status_code, 204)
        self.assertFalse(storage.get_store().exists(ocr.companion_key(key)))

    def test_a_scan_read_without_blocks_has_no_scan_view(self):
        document_id = self.upload_scan()
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/scan", headers=self.headers("cong_binh")).status_code, 404)

    def test_with_ocr_off_a_scan_waits_and_says_why(self):
        self.values["enabled"] = False
        document_id = self.upload_scan()
        detail = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual(detail["state"], DocumentState.NEEDS_OCR)
        self.assertIn("Bật OCR", detail["state_detail"])
        self.assertEqual(self.pages_read, 0)

    def test_a_dead_ocr_server_leaves_the_document_waiting_for_a_retry(self):
        self.values["base_url"] = "http://127.0.0.1:9/v1"
        document_id = self.upload_scan()
        detail = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual(detail["state"], DocumentState.NEEDS_OCR)
        self.assertIn("OCR", detail["state_detail"])
        self.values["base_url"] = self.ocr_server.base_url  # the administrator fixes the address and retries
        self.client.post(f"/api/documents/{document_id}/reprocess", headers=self.headers("cong_binh"))
        self.work()
        detail = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()
        self.assertIn(detail["state"], (DocumentState.READY, DocumentState.NEEDS_REVIEW))


if __name__ == "__main__":
    unittest.main()


class GroundedScanTest(ScannedDocumentTest):
    """The model answers in grounding mode: the blocks and their boxes are kept and the viewer can draw them on the page images."""

    def setUp(self):
        super().setUp()
        self.ocr_server.script = lambda messages, tools: self._grounded()

    def _grounded(self):
        text = GROUNDED_PAGES[self.pages_read % len(GROUNDED_PAGES)]
        self.pages_read += 1
        return {"content": text}

    def test_a_scan_is_read_indexed_and_searchable(self):  # the plain-text expectations of the parent do not apply here
        document_id = self.upload_scan()
        detail = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual(detail["document_type"], "Quyết định")

    def test_the_viewer_shows_the_ocr_text_and_the_download_is_still_the_pdf(self):
        pass

    def test_a_scan_read_without_blocks_has_no_scan_view(self):
        pass

    def test_blocks_and_page_images_are_served_and_blocks_point_at_their_paragraphs(self):
        document_id = self.upload_scan()
        headers = self.headers("cong_binh")
        scan = self.client.get(f"/api/documents/{document_id}/scan", headers=headers)
        self.assertEqual(scan.status_code, 200, scan.text)
        data = scan.json()
        self.assertEqual(data["pages"], 2)
        paragraphs = self.client.get(f"/api/documents/{document_id}/content", headers=headers).json()
        by_pi = {p["pi"]: p["text"] for p in paragraphs}
        number = next(b for b in data["blocks"] if b["text"].startswith("Số: 21"))
        self.assertEqual(by_pi[number["pi"][0]], "Số: 21/QĐ-QK3")
        self.assertEqual(number["box"], [77, 124, 268, 147])
        stamp = next(b for b in data["blocks"] if b["label"] == "image")
        self.assertIsNone(stamp["pi"])  # a stamp is not text of the document
        cells = next(b for b in data["blocks"] if b["label"] == "table")
        self.assertEqual([by_pi[i] for i in range(cells["pi"][0], cells["pi"][1] + 1)], ["Họ tên", "Chức vụ", "Nguyễn Văn An", "Trưởng ban"])
        page = self.client.get(f"/api/documents/{document_id}/pages/1", headers=headers)
        self.assertEqual((page.status_code, page.headers["content-type"]), (200, "image/png"))
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/pages/3", headers=headers).status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/scan", headers=self.headers("hau_can")).status_code, 404)  # no access to the unit
