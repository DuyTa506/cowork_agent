"""Object storage: the directory store, the S3 store (against a real MinIO when S3_TEST_ENDPOINT is set) and ranged downloads."""
import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from app import storage
from app.storage import BlobNotFound, LocalBlobStore
from app.storage.s3 import S3BlobStore

from test_documents_api import ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (module fixtures are reused)

S3_ENDPOINT = os.getenv("S3_TEST_ENDPOINT", "")  # e.g. 127.0.0.1:19000 (docker run minio/minio ... server /data)
S3_USER, S3_PASSWORD = os.getenv("S3_TEST_USER", "qk3test"), os.getenv("S3_TEST_PASSWORD", "qk3test-secret-1")


class StoreContract:
    """Behaviour every `BlobStore` must have; the concrete test cases provide `make_store`."""

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store = self.make_store()
        self.tmp = Path(tempfile.mkdtemp(prefix="qk3-blob-"))
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)

    def test_put_stat_open_roundtrip(self):
        data = os.urandom(300_000)
        self.store.put("documents/a.pdf", io.BytesIO(data), len(data))
        info = self.store.stat("documents/a.pdf")
        self.assertEqual((info.size, info.content_type), (len(data), "application/pdf"))
        stream = self.store.open("documents/a.pdf")
        self.assertEqual(b"".join(stream), data)

    def test_ranges(self):
        data = bytes(range(256)) * 1000
        self.store.put("documents/r.bin", io.BytesIO(data), len(data))
        self.assertEqual(b"".join(self.store.open("documents/r.bin", 1000, 50)), data[1000:1050])
        self.assertEqual(b"".join(self.store.open("documents/r.bin", len(data) - 10)), data[-10:])

    def test_put_file_replaces_and_download_copies(self):
        source = self.tmp / "s.docx"
        source.write_bytes(b"one")
        self.store.put_file("documents/x.docx", source)
        source.write_bytes(b"two-two")
        self.store.put_file("documents/x.docx", source)
        target = self.store.download("documents/x.docx", self.tmp / "out" / "copy.docx")
        self.assertEqual(target.read_bytes(), b"two-two")
        with self.store.local_copy("documents/x.docx", self.tmp / "scratch") as path:
            self.assertEqual((path.name, path.read_bytes()), ("x.docx", b"two-two"))

    def test_missing_objects(self):
        with self.assertRaises(BlobNotFound):
            self.store.stat("documents/none.docx")
        with self.assertRaises(BlobNotFound):
            self.store.open("documents/none.docx")
        self.assertFalse(self.store.exists("documents/none.docx"))
        self.store.delete("documents/none.docx")  # deleting nothing is fine

    def test_delete_and_delete_prefix(self):
        for name in ("chat/s1/a.docx", "chat/s1/b.docx", "chat/s2/a.docx"):
            self.store.put(name, io.BytesIO(b"x"), 1)
        self.assertEqual(self.store.delete_prefix("chat/s1/"), 2)
        self.assertFalse(self.store.exists("chat/s1/a.docx"))
        self.assertTrue(self.store.exists("chat/s2/a.docx"))
        self.store.delete("chat/s2/a.docx")
        self.assertFalse(self.store.exists("chat/s2/a.docx"))
        with self.assertRaises(ValueError):
            self.store.delete_prefix("")


class LocalStoreTest(StoreContract, unittest.TestCase):
    def make_store(self):
        return LocalBlobStore(Path(tempfile.mkdtemp(prefix="qk3-objects-")))

    def test_keys_cannot_escape_the_root(self):
        for key in ("../evil", "documents/../../evil", "/etc/passwd", ""):
            with self.assertRaises(ValueError):
                self.store.put(key, io.BytesIO(b"x"), 1)


@unittest.skipUnless(S3_ENDPOINT, "set S3_TEST_ENDPOINT to run against a real S3-compatible server")
class S3StoreTest(StoreContract, unittest.TestCase):
    def make_store(self):
        store = S3BlobStore(S3_ENDPOINT, S3_USER, S3_PASSWORD, "qk3-test-" + uuid.uuid4().hex[:8])
        store.ensure_bucket()
        self.addCleanup(self.drop, store)
        return store

    @staticmethod
    def drop(store: S3BlobStore) -> None:
        store.delete_prefix("chat/")
        store.delete_prefix("documents/")
        store._client.remove_bucket(store.bucket)


class RangedDownloadTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.doc_id = self.upload_and_process("cong_binh")
        self.url = f"/api/documents/{self.doc_id}/file"

    def test_whole_file_and_headers(self):
        reply = self.client.get(self.url, headers=self.headers("cong_binh"))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.headers["accept-ranges"], "bytes")
        self.assertEqual(int(reply.headers["content-length"]), len(reply.content))
        self.assertTrue(reply.content.startswith(b"PK"))
        self.assertIn("attachment", reply.headers["content-disposition"])
        self.assertIn("inline", self.client.get(self.url + "?inline=true", headers=self.headers("cong_binh")).headers["content-disposition"])

    def test_byte_ranges(self):
        whole = self.client.get(self.url, headers=self.headers("cong_binh")).content
        part = self.client.get(self.url, headers={**self.headers("cong_binh"), "Range": "bytes=10-19"})
        self.assertEqual((part.status_code, part.content), (206, whole[10:20]))
        self.assertEqual(part.headers["content-range"], f"bytes 10-19/{len(whole)}")
        tail = self.client.get(self.url, headers={**self.headers("cong_binh"), "Range": "bytes=-7"})
        self.assertEqual((tail.status_code, tail.content), (206, whole[-7:]))
        open_end = self.client.get(self.url, headers={**self.headers("cong_binh"), "Range": f"bytes={len(whole) - 3}-"})
        self.assertEqual(open_end.content, whole[-3:])
        beyond = self.client.get(self.url, headers={**self.headers("cong_binh"), "Range": f"bytes={len(whole) + 5}-"})
        self.assertEqual((beyond.status_code, beyond.headers["content-range"]), (416, f"bytes */{len(whole)}"))

    def test_other_units_get_nothing_and_a_missing_object_is_reported(self):
        self.assertEqual(self.client.get(self.url, headers=self.headers("hau_can")).status_code, 404)
        with self.sessions() as db:
            from app.models import Document
            storage.get_store().delete(storage.keys.document(db.get(Document, self.doc_id).stored_name))
        reply = self.client.get(self.url, headers=self.headers("cong_binh"))
        self.assertEqual(reply.status_code, 404)
        self.assertIn("kho lưu trữ", reply.json()["detail"])


@unittest.skipUnless(S3_ENDPOINT, "set S3_TEST_ENDPOINT to run against a real S3-compatible server")
class DocumentsOnS3Test(ApiTestCase):
    """Upload -> worker -> view -> download -> delete with the originals in a real bucket."""

    def setUp(self):
        super().setUp()
        self.s3 = S3BlobStore(S3_ENDPOINT, S3_USER, S3_PASSWORD, "qk3-test-" + uuid.uuid4().hex[:8])
        self.s3.ensure_bucket()
        storage.set_store(self.s3)
        self.addCleanup(lambda: (self.s3.delete_prefix("documents/"), self.s3._client.remove_bucket(self.s3.bucket)))

    def test_full_lifecycle(self):
        doc_id = self.upload_and_process("cong_binh")
        self.assertEqual(self.state_of(doc_id) in ("ready", "needs_review"), True)
        keys = [o.object_name for o in self.s3._client.list_objects(self.s3.bucket, prefix="documents/", recursive=True)]
        self.assertEqual(len(keys), 1)
        head = self.headers("cong_binh")
        content = self.client.get(f"/api/documents/{doc_id}/content", headers=head)
        self.assertEqual(content.status_code, 200)
        self.assertGreater(len(content.json()), 5)
        part = self.client.get(f"/api/documents/{doc_id}/file", headers={**head, "Range": "bytes=0-3"})
        self.assertEqual((part.status_code, part.content), (206, b"PK\x03\x04"))
        self.assertEqual(self.client.delete(f"/api/documents/{doc_id}", headers=head).status_code, 204)
        self.assertEqual(list(self.s3._client.list_objects(self.s3.bucket, prefix="documents/", recursive=True)), [])


if __name__ == "__main__":
    unittest.main()
