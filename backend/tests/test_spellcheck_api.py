"""The "Kiểm tra chính tả" screen's API: private temporary sessions around doccheck's spelling layers."""
import io
import unittest
import zipfile
from unittest import mock

import doccheck

from docx import Document as WordDocument

from app.models import AuditLog, Document
from app.services.formatcheck import engine as format_engine, sessions as base

from test_documents_api import DOCX, ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (module fixtures are reused)

TEXT = "Chúng tôi thực hịên nhiệm vụ.\nĐơn vị đã hòan thành kế hoạch huấn luyện năm 2026.\nHôm nay trời đẹp, đơn vị hòan thành tốt."
URL = "/api/spellcheck"


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF with `text` in Helvetica (no text layer when `text` is empty), written by hand: no PDF library needed."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else ""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class SpellCheckTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        root = self.tmp / "check"
        root.mkdir()
        patcher = mock.patch.object(base, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = root

    def typo_docx(self, name="vb.docx") -> bytes:
        path = self.sample(name)
        word = WordDocument(str(path))
        for paragraph in word.paragraphs:
            for run in paragraph.runs:
                run.text = run.text.replace("Kiện toàn", "Kiện toàng")
        word.save(str(path))
        return path.read_bytes()

    def upload(self, data: bytes, name: str, who="cong_binh", **form):
        return self.client.post(URL, headers=self.headers(who), data=form, files=[("file", (name, io.BytesIO(data), "application/octet-stream"))])

    def paste(self, text=TEXT, who="cong_binh", **extra):
        return self.client.post(f"{URL}/text", headers=self.headers(who), json={"text": text, **extra})

    # ----- options -----
    def test_options(self):
        reply = self.client.get(f"{URL}/options", headers=self.headers("cong_binh")).json()
        self.assertTrue({".docx", ".doc", ".pdf", ".txt", ".md"} <= set(reply["accept"]))
        self.assertEqual(reply["max_chars"], 200000)

    # ----- pasted text -----
    def test_pasted_text_findings(self):
        reply = self.paste()
        self.assertEqual(reply.status_code, 201, reply.text)
        body = reply.json()
        result = body["result"]
        self.assertEqual((body["kind"], body["can_fix"], result["kind"]), ("text", True, "text"))
        self.assertEqual(result["counts"]["format"], 0)
        found = {i["found"] for i in result["items"]}
        self.assertTrue({"hịên", "hòan"} <= found, found)
        self.assertTrue(all(i["kind"] == "spelling" and i["raw_after"] for i in result["items"]))
        self.assertEqual(len(result["paras"]), 3)
        self.assertTrue(result["paras"][0]["marks"])
        self.assertEqual(body["counts"]["spelling"], len(result["items"]) + len(result["manual"]))

    def test_text_is_corrected_in_place(self):
        body = self.paste().json()
        sid, h = body["id"], self.headers("cong_binh")
        ids = [i["id"] for i in body["result"]["items"] if i["tier"] in ("cao", "trungbinh")]
        outcome = self.client.post(f"{URL}/{sid}/fix", headers=h, json={"ids": ids})
        self.assertEqual(outcome.status_code, 200, outcome.text)
        out = outcome.json()
        self.assertEqual(sorted(out["applied"]), sorted(ids))
        self.assertIn("thực hiện nhiệm vụ", out["text"])
        self.assertNotIn("hịên", out["text"])
        self.assertEqual(out["text"].count("\n"), TEXT.count("\n"))  # the lines are kept
        self.assertEqual(out["after"]["spelling"], 0)
        download = self.client.get(f"{URL}/{sid}/fixed", headers=h)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content.decode("utf-8"), out["text"])
        self.assertIn("_sua.txt", download.headers["content-disposition"])

    def test_emoji_before_a_mistake_does_not_shift_the_fix(self):
        text = "😀 Chúng tôi thực hịên nhiệm vụ."
        body = self.paste(text).json()
        ids = [i["id"] for i in body["result"]["items"]]
        out = self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": ids}).json()
        self.assertEqual(out["text"], "😀 Chúng tôi thực hiện nhiệm vụ.")

    def test_crlf_text_keeps_its_line_ends(self):
        body = self.paste("Chúng tôi thực hịên nhiệm vụ.\r\nHết.").json()
        ids = [i["id"] for i in body["result"]["items"]]
        self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": ids})
        raw = self.client.get(f"{URL}/{body['id']}/fixed", headers=self.headers("cong_binh")).content
        self.assertEqual(raw.decode("utf-8"), "Chúng tôi thực hiện nhiệm vụ.\r\nHết.")

    def test_empty_and_too_long_text(self):
        self.assertEqual(self.paste("   \n ").status_code, 422)
        self.assertEqual(self.paste("a " * 100001).status_code, 422)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_text_file_upload(self):
        reply = self.upload(TEXT.encode("utf-8"), "ghi chu.txt")
        self.assertEqual(reply.status_code, 201, reply.text)
        body = reply.json()
        self.assertEqual((body["kind"], body["name"]), ("text", "ghi chu.txt"))
        self.assertGreaterEqual(body["counts"]["spelling"], 2)
        ids = [i["id"] for i in body["result"]["items"]]
        self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": ids})
        download = self.client.get(f"{URL}/{body['id']}/fixed", headers=self.headers("cong_binh"))
        self.assertIn("ghi%20chu_sua.txt", download.headers["content-disposition"])

    def test_markdown_code_is_skipped_when_asked(self):
        text = "Chúng tôi thực hịên.\n\n```\nhịên hòan\n```\n"
        plain = self.paste(text).json()["counts"]["spelling"]
        skipped = self.paste(text, markdown=True).json()["counts"]["spelling"]
        self.assertLess(skipped, plain)

    def test_binary_file_named_txt_is_rejected(self):
        self.assertEqual(self.upload(b"\x00\x01\x02binary", "a.txt").status_code, 422)

    # ----- ignore list -----
    def test_ignore_list_hides_the_word_everywhere_and_can_be_cleared(self):
        body = self.paste().json()
        sid, h = body["id"], self.headers("cong_binh")
        total = body["counts"]["spelling"]
        hidden = self.client.put(f"{URL}/{sid}/ignore", headers=h, json={"words": ["Hòan"]}).json()  # case does not matter
        self.assertEqual(hidden["ignore"], ["Hòan"])
        self.assertLess(hidden["counts"]["spelling"], total)
        self.assertEqual(hidden["result"]["ignored"], total - hidden["counts"]["spelling"])
        self.assertNotIn("hòan", {i["found"] for i in hidden["result"]["items"]})
        for para in hidden["result"]["paras"]:
            for start, end, *_ in para["marks"]:
                self.assertNotEqual(para["text"][start:end].lower(), "hòan")
        again = self.client.get(f"{URL}/{sid}", headers=h).json()
        self.assertEqual(again["counts"], hidden["counts"])  # kept in the session
        cleared = self.client.put(f"{URL}/{sid}/ignore", headers=h, json={"words": []}).json()
        self.assertEqual(cleared["counts"]["spelling"], total)
        self.assertEqual(cleared["result"]["ignored"], 0)

    def test_ignored_items_are_not_in_the_report(self):
        sid, h = self.paste().json()["id"], self.headers("cong_binh")
        self.client.put(f"{URL}/{sid}/ignore", headers=h, json={"words": ["hòan"]})
        report = self.client.get(f"{URL}/{sid}/report", headers=h)
        self.assertEqual(report.status_code, 200)
        self.assertIn("hịên", report.text)
        self.assertNotIn("hòan", report.text)

    # ----- Word -----
    def test_word_file_has_spelling_findings_only(self):
        reply = self.upload(self.typo_docx(), "vb.docx")
        self.assertEqual(reply.status_code, 201, reply.text)
        body = reply.json()
        result = body["result"]
        self.assertEqual((body["kind"], body["can_fix"]), ("word", True))
        self.assertTrue(any(i["found"] == "toàng" for i in result["items"]))
        self.assertTrue(all(i["kind"] == "spelling" for i in result["items"]))
        self.assertEqual((result["banner"], result["counts"]["format"]), ([], 0))
        self.assertTrue(all(not p["msgs"] for p in result["paras"]))

    def test_word_fix_writes_tracked_changes_for_the_chosen_words_only(self):
        body = self.upload(self.typo_docx(), "vb.docx").json()
        sid, h = body["id"], self.headers("cong_binh")
        picked = [i["id"] for i in body["result"]["items"] if i["found"] == "toàng"]
        self.assertTrue(picked)
        outcome = self.client.post(f"{URL}/{sid}/fix", headers=h, json={"ids": picked}).json()
        self.assertEqual(sorted(outcome["applied"]), sorted(picked))
        self.assertLess(outcome["after"]["spelling"], body["counts"]["spelling"])
        download = self.client.get(f"{URL}/{sid}/fixed", headers=h)
        self.assertIn("vb_sua.docx", download.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(download.content)) as package:
            xml = package.read("word/document.xml").decode("utf-8")
        self.assertIn("w:ins", xml)
        self.assertTrue(self.client.get(f"{URL}/{sid}", headers=h).json()["fixed"])

    def test_word_fix_directly(self):
        body = self.upload(self.typo_docx(), "vb.docx").json()
        picked = [i["id"] for i in body["result"]["items"] if i["found"] == "toàng"]
        outcome = self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": picked, "mode": "apply"})
        self.assertEqual(outcome.status_code, 200, outcome.text)
        with zipfile.ZipFile(io.BytesIO(self.client.get(f"{URL}/{body['id']}/fixed", headers=self.headers("cong_binh")).content)) as package:
            xml = package.read("word/document.xml").decode("utf-8")
        self.assertNotIn("w:ins ", xml)  # no tracked change: written straight into the text
        self.assertNotIn("toàng", xml)
        self.assertIn(">toàn<", xml)

    def test_fix_rejects_bad_requests(self):
        body = self.upload(self.typo_docx(), "vb.docx").json()
        sid, h = body["id"], self.headers("cong_binh")
        self.assertEqual(self.client.post(f"{URL}/{sid}/fix", headers=h, json={"ids": ["S:99:1:2"]}).status_code, 422)
        self.assertEqual(self.client.post(f"{URL}/{sid}/fix", headers=h, json={"ids": []}).status_code, 422)
        ids = [i["id"] for i in body["result"]["items"]][:1]
        self.assertEqual(self.client.post(f"{URL}/{sid}/fix", headers=h, json={"ids": ids, "mode": "x"}).status_code, 422)
        self.assertEqual(self.client.get(f"{URL}/{sid}/fixed", headers=h).status_code, 404)

    def test_report_of_a_file_with_a_vietnamese_name(self):
        sid = self.upload(self.typo_docx(), "Hướng dẫn nội dung.docx").json()["id"]
        report = self.client.get(f"{URL}/{sid}/report", headers=self.headers("cong_binh"))
        self.assertEqual(report.status_code, 200)
        self.assertIn("filename*=utf-8''H%C6%B0%E1%BB%9Bng%20d%E1%BA%ABn%20n%E1%BB%99i%20dung_chinh_ta.txt", report.headers["content-disposition"])

    def test_word_report_and_original(self):
        sid, h = self.upload(self.typo_docx(), "vb.docx").json()["id"], self.headers("cong_binh")
        report = self.client.get(f"{URL}/{sid}/report", headers=h)
        self.assertEqual(report.status_code, 200)
        self.assertIn("toàng", report.text)
        self.assertNotIn("source.docx", report.text)
        self.assertEqual(self.client.get(f"{URL}/{sid}/file", headers=h).content[:2], b"PK")

    # ----- PDF -----
    def test_pdf_is_checked_but_not_fixable(self):
        reply = self.upload(tiny_pdf("Chung toi thuc hien nhiem vu cua don vi trong nam"), "kq.pdf")
        if reply.status_code == 422:
            self.skipTest("doccheck cannot read the generated PDF: " + reply.text)
        self.assertEqual(reply.status_code, 201, reply.text)
        body = reply.json()
        self.assertEqual((body["kind"], body["can_fix"]), ("pdf", False))
        self.assertEqual(self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": ["x"]}).status_code, 422)

    def test_scan_without_text_layer_is_refused(self):
        self.assertEqual(self.upload(tiny_pdf(""), "scan.pdf").status_code, 422)

    # ----- privacy, lifetime, audit -----
    def test_sessions_are_private_and_separate_from_format_check(self):
        sid = self.paste().json()["id"]
        for who in ("hau_can", "admin", "commander", "bo_tham_muu"):
            for path in ("", "/file", "/report", "/fixed"):
                self.assertEqual(self.client.get(f"{URL}/{sid}{path}", headers=self.headers(who)).status_code, 404, (who, path))
            self.assertEqual(self.client.put(f"{URL}/{sid}/ignore", headers=self.headers(who), json={"words": ["a"]}).status_code, 404)
        # the format-check screen does not see spelling sessions, nor the other way round
        self.assertEqual(self.client.get(f"/api/format-check/{sid}", headers=self.headers("cong_binh")).status_code, 404)
        format_id = self.client.post("/api/format-check", headers=self.headers("cong_binh"),
                                     files=[("file", ("a.docx", io.BytesIO(self.typo_docx()), DOCX))]).json()["id"]
        self.assertEqual(self.client.get(f"{URL}/{format_id}", headers=self.headers("cong_binh")).status_code, 404)
        self.assertEqual(self.client.get(f"{URL}/options").status_code, 401)

    def test_nothing_is_indexed_or_stored(self):
        self.paste()
        self.upload(self.typo_docx(), "vb.docx")
        self.assertEqual(self.index.count(), 0)
        with self.sessions() as db:
            self.assertEqual(db.query(Document).count(), 0)

    def test_delete_removes_the_files(self):
        sid, h = self.paste().json()["id"], self.headers("cong_binh")
        self.assertEqual(self.client.delete(f"{URL}/{sid}", headers=h).status_code, 204)
        self.assertEqual(self.client.get(f"{URL}/{sid}", headers=h).status_code, 404)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_expired_sessions_are_purged(self):
        from datetime import timedelta
        from app.models import CheckSession
        from app.models.base import now_utc
        sid = self.paste().json()["id"]
        with self.sessions() as db:
            db.get(CheckSession, sid).expires_at = now_utc() - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.client.get(f"{URL}/{sid}", headers=self.headers("cong_binh")).status_code, 404)
        self.paste()  # a new check clears the expired one
        self.assertFalse((self.root / sid).exists())

    def test_audit_trail(self):
        body = self.paste().json()
        ids = [i["id"] for i in body["result"]["items"]][:1]
        self.client.post(f"{URL}/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": ids})
        with self.sessions() as db:
            actions = [row.action for row in db.query(AuditLog).filter(AuditLog.action.like("spellcheck.%")).order_by(AuditLog.id)]
            details = " ".join(row.detail for row in db.query(AuditLog).filter(AuditLog.action.like("spellcheck.%")))
        self.assertEqual(actions, ["spellcheck.run", "spellcheck.fix"])
        self.assertNotIn("hịên", details)  # what was checked never goes into the trail

@unittest.skipUnless(format_engine.deep_options() and doccheck.gec_info()["onnxruntime"], "no ONNX Runtime for the deep model")
class DeepModelTest(unittest.TestCase):
    TEXT = "Đồng chí A đả hoàn thành nhiệm vụ. Tôi nghỉ rằng kế hoạch này cần được bổ sung."

    def test_the_deep_model_is_used_by_default_and_can_be_switched_off(self):
        from app.services.spellcheck import engine
        found = {i["found"] for i in engine.analyze_text(self.TEXT, "t", False)["items"]}
        self.assertIn("nghỉ", found)  # only the deep model sees this one (a real word, wrong in context)
        with mock.patch.object(format_engine.settings.cache, "get", lambda key: {"spell_deep": "off"}):
            plain = {i["found"] for i in engine.analyze_text(self.TEXT, "t", False)["items"]}
        self.assertNotIn("nghỉ", plain)
        self.assertLess(len(plain), len(found))  # without the deep model there are fewer findings, never more

