"""Tags on documents: computed at processing, edited by hand, filtered and counted for the filter panel."""
import unittest

from app.services import tagging
from test_documents_api import ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (the shared index collection)


class AutoTagTests(unittest.TestCase):
    def test_year_topics_and_scan_marker(self):
        tags = tagging.auto_tags(title="Kế hoạch tổ chức diễn tập khu vực phòng thủ năm 2026", issued_date="2026-10-15",
                                 head="Tổ chức diễn tập, huấn luyện.", scanned=True)
        self.assertEqual(tags[0], "Năm 2026")
        self.assertIn("Diễn tập", tags)
        self.assertIn("Sẵn sàng chiến đấu", tags)
        self.assertEqual(tags[-1], "Bản scan (OCR)")
        self.assertLessEqual(len([t for t in tags if t not in ("Năm 2026", "Bản scan (OCR)")]), 3)

    def test_a_topic_needs_the_title_or_repeated_mentions(self):
        self.assertEqual(tagging.auto_tags(title="Công văn", issued_date="", head="Có một lần nhắc đến kinh phí.", scanned=False), [])
        self.assertIn("Tài chính", tagging.auto_tags(title="Công văn", issued_date="", head="kinh phí; ngân sách; quyết toán.", scanned=False))
        self.assertIn("Tài chính", tagging.auto_tags(title="Về việc cấp kinh phí", issued_date="", head="", scanned=False))

    def test_clean_tidies_and_bounds(self):
        self.assertEqual(tagging.clean([" Khẩn ", "khẩn", "Hội  nghị,  quý III", ""]), ["Khẩn", "Hội nghị quý III"])
        from app.core.errors import ValidationFailed
        with self.assertRaises(ValidationFailed):
            tagging.clean(["x" * 41])
        with self.assertRaises(ValidationFailed):
            tagging.clean([f"t{i}" for i in range(13)])


class TagApiTest(ApiTestCase):
    def test_processing_tags_a_document_and_the_list_can_filter_by_tag(self):
        first = self.upload_and_process("cong_binh")
        listed = self.client.get("/api/documents", headers=self.headers("cong_binh")).json()
        item = next(i for i in listed["items"] if i["id"] == first)
        self.assertTrue(any(t.startswith("Năm ") for t in item["tags"]), item["tags"])
        year = next(t for t in item["tags"] if t.startswith("Năm "))
        hit = self.client.get("/api/documents", headers=self.headers("cong_binh"), params={"tag": year}).json()
        self.assertIn(first, [i["id"] for i in hit["items"]])
        miss = self.client.get("/api/documents", headers=self.headers("cong_binh"), params={"tag": "không có thẻ này"}).json()
        self.assertEqual(miss["total"], 0)
        kind = next(i for i in listed["items"] if i["id"] == first)["document_type"]
        both = self.client.get("/api/documents", headers=self.headers("cong_binh"), params={"document_type": f"{kind},Loại khác"}).json()
        self.assertIn(first, [i["id"] for i in both["items"]])  # several types are an OR

    def test_hand_made_tags_survive_reprocessing_and_only_managers_set_them(self):
        document_id = self.upload_and_process("cong_binh")
        url = f"/api/documents/{document_id}/tags"
        reply = self.client.put(url, headers=self.headers("cong_binh"), json={"tags": ["Khẩn", "Quý III"]})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("Khẩn", reply.json()["tags"])
        self.assertEqual(sorted(reply.json()["manual_tags"]), ["Khẩn", "Quý III"])
        self.assertEqual(self.client.put(url, headers=self.headers("bo_tham_muu"), json={"tags": ["x"]}).status_code, 403)  # not the uploader
        self.client.post(f"/api/documents/{document_id}/reprocess", headers=self.headers("cong_binh"))
        self.work()
        tags = self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()["tags"]
        self.assertIn("Khẩn", tags)
        self.assertEqual(self.client.put(url, headers=self.headers("cong_binh"), json={"tags": [f"t{i}" for i in range(13)]}).status_code, 422)
        self.client.put(url, headers=self.headers("cong_binh"), json={"tags": []})
        self.assertNotIn("Khẩn", self.client.get(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).json()["tags"])

    def test_facets_count_only_what_the_user_may_read(self):
        self.upload_and_process("cong_binh")
        mine = self.client.get("/api/documents/facets", headers=self.headers("cong_binh")).json()
        self.assertEqual(sum(v["count"] for v in mine["types"]), 1)
        self.assertTrue(mine["years"])
        self.assertEqual(mine["units"], [{"value": "btm.cong_binh", "count": 1}])
        other = self.client.get("/api/documents/facets", headers=self.headers("hau_can")).json()  # a sibling unit sees nothing of it
        self.assertEqual((other["units"], other["types"], other["years"], other["tags"]), ([], [], [], []))

    def test_deleting_a_document_removes_its_tags(self):
        from sqlalchemy import select
        from app.models import DocumentTag
        document_id = self.upload_and_process("cong_binh")
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).status_code, 204)
        with self.sessions() as db:
            self.assertEqual(db.scalars(select(DocumentTag).where(DocumentTag.document_id == document_id)).all(), [])


if __name__ == "__main__":
    unittest.main()
