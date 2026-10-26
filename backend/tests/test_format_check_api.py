"""The "Kiểm tra thể thức" screen's API: private temporary sessions around doccheck."""
import io
import zipfile
from datetime import datetime, timedelta
from unittest import mock

from docx import Document as WordDocument

from app.models import CheckSession, Document
from app.models.base import now_utc
from app.services.formatcheck import sessions

from test_documents_api import DOCX, ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (module fixtures are reused)


class FormatCheckTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        root = self.tmp / "check"
        root.mkdir()
        patcher = mock.patch.object(sessions, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = root

    def typo_docx(self, name="vb.docx") -> bytes:
        """A decision with a misspelt word ("toàng") and ordinary format problems."""
        path = self.sample(name)
        word = WordDocument(str(path))
        for paragraph in word.paragraphs:
            for run in paragraph.runs:
                run.text = run.text.replace("Kiện toàn", "Kiện toàng")
        word.save(str(path))
        return path.read_bytes()

    def check(self, who="cong_binh", data: bytes | None = None, name="vb.docx", **form):
        data = data if data is not None else self.typo_docx(name)
        return self.client.post("/api/format-check", headers=self.headers(who), data=form, files=[("file", (name, io.BytesIO(data), DOCX))])

    def test_options(self):
        reply = self.client.get("/api/format-check/options", headers=self.headers("cong_binh")).json()
        self.assertEqual(reply["default_profile"], "tt68")
        self.assertEqual({p["id"] for p in reply["profiles"]}, {"tt68", "nd30"})
        self.assertIn(".docx", reply["accept"])

    def test_check_returns_findings_selectable_fixes_and_a_deadline(self):
        reply = self.check()
        self.assertEqual(reply.status_code, 201, reply.text)
        body = reply.json()
        result = body["result"]
        self.assertTrue(body["can_fix"])
        self.assertEqual(result["facts"]["doc_type"], "QĐ")
        self.assertGreater(result["counts"]["format"], 0)
        self.assertGreaterEqual(result["counts"]["spelling"], 1)
        self.assertTrue(result["items"] and result["manual"] and result["paras"])
        self.assertTrue(all({"id", "label", "before", "after", "tier", "kind"} <= set(i) for i in result["items"]))
        expires = datetime.fromisoformat(body["expires_at"])
        self.assertAlmostEqual((expires - now_utc()).total_seconds(), 24 * 3600, delta=120)
        again = self.client.get(f"/api/format-check/{body['id']}", headers=self.headers("cong_binh")).json()
        self.assertEqual(again["result"]["counts"], result["counts"])

    def test_nothing_is_indexed_or_stored(self):
        self.check()
        self.assertEqual(self.index.count(), 0)
        with self.sessions() as db:
            self.assertEqual(db.query(Document).count(), 0)

    def test_sessions_are_private_even_from_admins(self):
        sid = self.check().json()["id"]
        for who in ("hau_can", "admin", "commander", "bo_tham_muu"):
            self.assertEqual(self.client.get(f"/api/format-check/{sid}", headers=self.headers(who)).status_code, 404, who)
            self.assertEqual(self.client.get(f"/api/format-check/{sid}/file", headers=self.headers(who)).status_code, 404, who)
            self.assertEqual(self.client.post(f"/api/format-check/{sid}/fix", headers=self.headers(who), json={"ids": ["x"]}).status_code, 404, who)
        self.assertEqual(self.client.get("/api/format-check/options").status_code, 401)

    def test_fix_selected_items_writes_tracked_changes(self):
        body = self.check().json()
        sid = body["id"]
        picked = [i["id"] for i in body["result"]["items"] if i["tier"] in ("cao", "trungbinh")]
        self.assertTrue(picked)
        fixed = self.client.post(f"/api/format-check/{sid}/fix", headers=self.headers("cong_binh"), json={"ids": picked})
        self.assertEqual(fixed.status_code, 200, fixed.text)
        outcome = fixed.json()
        self.assertEqual(sorted(outcome["applied"]), sorted(picked))
        self.assertLess(outcome["after"]["format"], body["counts"]["format"])
        download = self.client.get(f"/api/format-check/{sid}/fixed", headers=self.headers("cong_binh"))
        self.assertEqual(download.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(download.content)) as package:
            xml = package.read("word/document.xml").decode("utf-8")
        self.assertTrue("w:rPrChange" in xml or "w:pPrChange" in xml or "w:sectPrChange" in xml)
        self.assertTrue(self.client.get(f"/api/format-check/{sid}", headers=self.headers("cong_binh")).json()["fixed"])

    def test_fix_only_what_was_chosen(self):
        body = self.check().json()
        one = body["result"]["items"][0]["id"]
        outcome = self.client.post(f"/api/format-check/{body['id']}/fix", headers=self.headers("cong_binh"), json={"ids": [one]}).json()
        self.assertEqual(outcome["applied"], [one])

    def test_fix_rejects_unknown_ids_and_empty_selection(self):
        sid = self.check().json()["id"]
        h = self.headers("cong_binh")
        self.assertEqual(self.client.post(f"/api/format-check/{sid}/fix", headers=h, json={"ids": ["F:nope:p9"]}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/format-check/{sid}/fix", headers=h, json={"ids": []}).status_code, 422)
        self.assertEqual(self.client.get(f"/api/format-check/{sid}/fixed", headers=h).status_code, 404)

    def test_recheck_with_another_profile_and_without_spelling(self):
        sid = self.check().json()["id"]
        h = self.headers("cong_binh")
        other = self.client.post(f"/api/format-check/{sid}/recheck", headers=h, json={"profile": "nd30", "spell": False}).json()
        self.assertEqual((other["profile"], other["spell"], other["counts"]["spelling"]), ("nd30", False, 0))
        self.assertEqual(self.client.post(f"/api/format-check/{sid}/recheck", headers=h, json={"profile": "khong-co"}).status_code, 422)

    def test_rejects_bad_input(self):
        self.assertEqual(self.check(data=b"hello", name="a.txt").status_code, 422)
        self.assertEqual(self.check(data=b"not a word file", name="a.docx").status_code, 422)
        self.assertEqual(self.check(data=b"", name="a.docx").status_code, 422)
        self.assertEqual(self.check(profile="khong-co").status_code, 422)
        self.assertEqual(list(self.root.iterdir()), [])  # failed checks leave nothing behind

    def test_downloads(self):
        sid = self.check().json()["id"]
        h = self.headers("cong_binh")
        report = self.client.get(f"/api/format-check/{sid}/report", headers=h)
        self.assertEqual(report.status_code, 200)
        self.assertIn("charset=utf-8", report.headers["content-type"])
        self.assertTrue(report.text.strip())
        self.assertNotIn("source.docx", report.text)  # the server-side path is not shown to the user
        annotated = self.client.get(f"/api/format-check/{sid}/annotated", headers=h)
        self.assertEqual((annotated.status_code, annotated.content[:2]), (200, b"PK"))
        self.assertEqual(self.client.get(f"/api/format-check/{sid}/file", headers=h).content[:2], b"PK")

    def test_report_of_a_file_with_a_vietnamese_name(self):
        sid = self.check(name="Quyết định số 15.docx").json()["id"]
        report = self.client.get(f"/api/format-check/{sid}/report", headers=self.headers("cong_binh"))
        self.assertEqual(report.status_code, 200)
        self.assertIn("filename*=utf-8''Quy%E1%BA%BFt", report.headers["content-disposition"])

    def test_save_to_store_is_the_only_way_in(self):
        body = self.check().json()
        sid, h = body["id"], self.headers("cong_binh")
        ids = [i["id"] for i in body["result"]["items"] if i["tier"] == "cao"]
        self.client.post(f"/api/format-check/{sid}/fix", headers=h, json={"ids": ids})
        saved = self.client.post(f"/api/format-check/{sid}/save", headers=h, json={"which": "fixed"})
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual((saved.json()["state"], saved.json()["unit_id"]), ("uploaded", "btm.cong_binh"))
        self.work()
        self.assertGreater(self.index.count(), 0)
        self.assertEqual(self.client.post(f"/api/format-check/{sid}/save", headers=h, json={"which": "weird"}).status_code, 422)

    def test_save_fixed_before_fixing_is_not_found(self):
        sid = self.check().json()["id"]
        self.assertEqual(self.client.post(f"/api/format-check/{sid}/save", headers=self.headers("cong_binh"), json={"which": "fixed"}).status_code, 404)

    def test_delete_and_expiry(self):
        h = self.headers("cong_binh")
        first = self.check().json()["id"]
        self.assertEqual(self.client.delete(f"/api/format-check/{first}", headers=h).status_code, 204)
        self.assertEqual(self.client.get(f"/api/format-check/{first}", headers=h).status_code, 404)
        self.assertFalse((self.root / first).exists())

        second = self.check(name="two.docx").json()["id"]
        with self.sessions() as db:
            db.get(CheckSession, second).expires_at = now_utc() - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.client.get(f"/api/format-check/{second}", headers=h).status_code, 404)
        with self.sessions() as db:
            self.assertEqual(sessions.purge_expired(db), 1)
            db.commit()
        self.assertFalse((self.root / second).exists())

    def test_orphan_directories_are_cleaned_but_fresh_ones_are_kept(self):
        import os
        old, fresh = self.root / "old", self.root / "fresh"
        old.mkdir()
        fresh.mkdir()
        past = now_utc().timestamp() - 7200
        os.utime(old, (past, past))
        with self.sessions() as db:
            sessions.purge_expired(db)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_pdf_without_text_layer_is_refused_and_pdf_with_text_is_check_only(self):
        blank = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
        reply = self.client.post("/api/format-check", headers=self.headers("cong_binh"), files=[("file", ("scan.pdf", io.BytesIO(blank), "application/pdf"))])
        self.assertEqual(reply.status_code, 422, reply.text)
