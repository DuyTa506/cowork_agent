import unittest

from app import storage
from app.models import Document
from app.services import preview
from test_documents_api import ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (module fixtures are reused)


@unittest.skipUnless(preview.available(), "LibreOffice (soffice) is not installed")
class PreviewTest(ApiTestCase):
    def key_of(self, document_id: int) -> str:
        with self.sessions() as db:
            return storage.keys.document(db.get(Document, document_id).stored_name)

    def test_a_word_file_gets_a_pdf_view_when_it_is_processed_and_it_is_served_with_ranges(self):
        document_id = self.upload_and_process()
        key = self.key_of(document_id)
        self.assertTrue(storage.get_store().exists(preview.view_key(key)))  # made by the worker, not at the first view
        headers = self.headers("cong_binh")
        whole = self.client.get(f"/api/documents/{document_id}/preview", headers=headers)
        self.assertEqual((whole.status_code, whole.headers["content-type"]), (200, "application/pdf"))
        self.assertTrue(whole.content.startswith(b"%PDF"))
        self.assertIn("max-age", whole.headers["cache-control"])
        part = self.client.get(f"/api/documents/{document_id}/preview", headers={**headers, "Range": "bytes=0-9"})
        self.assertEqual((part.status_code, part.content), (206, whole.content[:10]))

    def test_a_missing_view_is_built_on_the_first_request_for_documents_from_before(self):
        document_id = self.upload_and_process()
        key = self.key_of(document_id)
        storage.get_store().delete(preview.view_key(key))
        reply = self.client.get(f"/api/documents/{document_id}/preview", headers=self.headers("cong_binh"))
        self.assertEqual(reply.status_code, 200)
        self.assertTrue(storage.get_store().exists(preview.view_key(key)))

    def test_nobody_without_access_gets_the_view_and_delete_removes_it(self):
        document_id = self.upload_and_process()
        key = self.key_of(document_id)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/preview", headers=self.headers("hau_can")).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}", headers=self.headers("cong_binh")).status_code, 204)
        self.assertFalse(storage.get_store().exists(preview.view_key(key)))


if __name__ == "__main__":
    unittest.main()
