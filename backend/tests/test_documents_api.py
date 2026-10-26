"""End to end: upload through the API, process with the worker, read back with permissions.

The database is in memory and the upload directory is temporary. The search index is a real Qdrant collection (like the other
search tests) with the hash embedder, so no model server is needed.
"""
import io
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from sqlalchemy.orm import sessionmaker

from app import storage
from app.core import config, security
from app.core.database import get_db
from app.main import create_app
from app.models import Document, DocumentState, Job
from app.search import HashEmbedder, QdrantIndex
from app.storage import LocalBlobStore
from app.services import indexing, users
from app.worker import runner

from support import memory_engine
from test_parsing import build_decision

security._HASH_ROUNDS = 1_000  # real hashing is deliberately slow; these tests create dozens of accounts

URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
KEY = os.getenv("QDRANT_API_KEY", "ChangeQdrantKey_2026")
PASSWORD = "Matkhau-thu-nghiem-1"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


COLLECTION = "qk3_test_api_" + uuid.uuid4().hex[:8]
INDEX = QdrantIndex(QdrantClient(url=URL, api_key=KEY), HashEmbedder(64), COLLECTION)


def setUpModule():
    """One collection for the whole module: creating one costs ~17 requests, far more than the tests themselves."""
    INDEX.ensure_collection()


def tearDownModule():
    INDEX.client.delete_collection(COLLECTION)


class ApiTestCase(unittest.TestCase):
    """Builds the app on an in-memory database with three units' worth of accounts."""

    def setUp(self):
        self.engine = memory_engine()
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.tmp = Path(tempfile.mkdtemp(prefix="qk3-api-"))
        self.objects = self.tmp / "objects"
        self.uploads = self.objects / "documents"  # where the store keeps the originals
        self.uploads.mkdir(parents=True)
        storage.set_store(LocalBlobStore(self.objects))
        self.addCleanup(storage.set_store, None)
        self.collection, self.index = COLLECTION, INDEX
        self.index.client.delete(COLLECTION, points_selector=models.FilterSelector(filter=models.Filter()), wait=True)
        for patcher in (
            mock.patch.object(config, "TEMP_DIR", self.tmp / "tmp"),
            mock.patch.object(indexing, "current", lambda values=None: self.index),
            mock.patch.object(indexing, "store_only", lambda values=None: self.index),
            mock.patch.object(indexing, "fingerprint", lambda values=None: "test"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        app = create_app()  # not entered as a context manager, so the start-up hook (real database) does not run

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        with self.sessions() as db:
            self.accounts = {
                "admin": users.create(db, username="admin", password=PASSWORD, full_name="Admin", unit_id="btl", role="admin"),
                "commander": users.create(db, username="chihuy", password=PASSWORD, full_name="Chỉ huy", unit_id="btl", role="commander"),
                "cong_binh": users.create(db, username="congbinh", password=PASSWORD, full_name="Công binh", unit_id="btm.cong_binh", role="staff"),
                "hau_can": users.create(db, username="haucan", password=PASSWORD, full_name="Hậu cần", unit_id="btm.hau_can", role="staff"),
                "bo_tham_muu": users.create(db, username="btm", password=PASSWORD, full_name="Bộ Tham mưu", unit_id="btm", role="staff"),
            }
            db.commit()
        self.tokens: dict[str, dict] = {}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ----- helpers -----
    def headers(self, who: str) -> dict:
        if who not in self.tokens:
            username = {"admin": "admin", "commander": "chihuy", "cong_binh": "congbinh", "hau_can": "haucan", "bo_tham_muu": "btm"}[who]
            reply = self.client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
            self.assertEqual(reply.status_code, 200, reply.text)
            self.tokens[who] = {"Authorization": "Bearer " + reply.json()["access_token"]}
        return self.tokens[who]

    def sample(self, name: str = "qd.docx", **kwargs) -> Path:
        path = self.tmp / name
        build_decision(path, **kwargs)
        return path

    def upload(self, who: str, path: Path, *, secret: bool = False, name: str | None = None):
        with open(path, "rb") as fh:
            return self.client.post("/api/documents", headers=self.headers(who), data={"declared_secret": str(secret).lower()},
                                    files=[("files", (name or path.name, fh, DOCX))])

    def work(self) -> int:
        """Runs the worker until the queue is empty; returns how many jobs it handled."""
        done = 0
        while runner.run_once(self.sessions):
            done += 1
        return done

    def upload_and_process(self, who: str = "cong_binh", **kwargs) -> int:
        reply = self.upload(who, self.sample(**kwargs))
        self.assertEqual(reply.status_code, 201, reply.text)
        item = reply.json()["items"][0]
        self.assertEqual(item["error"], "", item)
        self.work()
        return item["document"]["id"]

    def state_of(self, document_id: int) -> str:
        with self.sessions() as db:
            return db.get(Document, document_id).state


class UploadAndPermissionTest(ApiTestCase):
    def test_upload_is_queued_then_processed(self):
        reply = self.upload("cong_binh", self.sample())
        self.assertEqual(reply.status_code, 201, reply.text)
        document = reply.json()["items"][0]["document"]
        self.assertEqual(document["state"], DocumentState.UPLOADED)
        self.assertEqual(document["unit_id"], "btm.cong_binh")
        self.assertEqual(self.work(), 1)
        detail = self.client.get(f"/api/documents/{document['id']}", headers=self.headers("cong_binh")).json()
        self.assertIn(detail["state"], (DocumentState.READY, DocumentState.NEEDS_REVIEW))
        self.assertEqual(detail["document_type"], "Quyết định")
        self.assertEqual(detail["document_number"], "15")
        self.assertGreater(detail["chunk_count"], 0)
        self.assertEqual([s["state"] for s in detail["steps"]], ["done"] * 4)
        self.assertEqual(self.index.count(str(document["id"])), detail["chunk_count"])

    def test_duplicate_in_same_unit_is_rejected_with_existing_id(self):
        path = self.sample()  # built once: python-docx stamps the time, so two builds are not byte-identical
        first = self.upload("cong_binh", path).json()["items"][0]["document"]["id"]
        again = self.upload("cong_binh", path).json()["items"][0]
        self.assertEqual((again["code"], again["existing_id"]), ("duplicate", first))
        # another unit may hold the same file
        other = self.upload("hau_can", path).json()["items"][0]
        self.assertEqual(other["error"], "")

    def test_rejects_bad_files_without_stopping_the_batch(self):
        good = self.sample().read_bytes()
        files = [("files", ("notes.txt", io.BytesIO(b"hello"), "text/plain")),
                 ("files", ("fake.docx", io.BytesIO(b"this is not a word file"), DOCX)),
                 ("files", ("empty.docx", io.BytesIO(b""), DOCX)),
                 ("files", ("../../evil/real.docx", io.BytesIO(good), DOCX))]
        reply = self.client.post("/api/documents", headers=self.headers("cong_binh"), files=files)
        items = reply.json()["items"]
        self.assertEqual([bool(i["error"]) for i in items], [True, True, True, False])
        self.assertEqual(items[3]["document"]["original_name"], "real.docx")
        self.assertEqual(len(list(self.uploads.iterdir())), 1)  # failed uploads leave nothing behind

    def test_size_limit_comes_from_settings(self):
        from app.services import settings
        with self.sessions() as db:
            settings.save(db, "storage", {"upload_max_mb": 1}, actor="t")
        big = io.BytesIO(b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10))
        reply = self.client.post("/api/documents", headers=self.headers("cong_binh"), files=[("files", ("big.pdf", big, "application/pdf"))])
        self.assertIn("vượt quá 1 MB", reply.json()["items"][0]["error"])

    def test_documents_are_visible_to_the_unit_and_its_parents_only(self):
        doc_id = self.upload_and_process("cong_binh")
        for who, seen in (("cong_binh", True), ("bo_tham_muu", True), ("commander", True), ("admin", True), ("hau_can", False)):
            reply = self.client.get(f"/api/documents/{doc_id}", headers=self.headers(who))
            self.assertEqual(reply.status_code, 200 if seen else 404, who)
            listed = [d["id"] for d in self.client.get("/api/documents", headers=self.headers(who)).json()["items"]]
            self.assertEqual(doc_id in listed, seen, who)
        counts = self.client.get("/api/documents", headers=self.headers("hau_can")).json()
        self.assertEqual((counts["total"], counts["states"]), (0, {}))

    def test_filters_cover_combined_number_symbol_several_states_subtree_and_level(self):
        mine = self.upload_and_process("cong_binh")
        secret = self.upload("cong_binh", self.sample("mat.docx", number="16"), secret=True).json()["items"][0]["document"]["id"]
        self.work()
        queued = self.upload("bo_tham_muu", self.sample("moi.docx", number="17")).json()["items"][0]["document"]["id"]
        head = self.headers("commander")

        def ids(**params) -> set[int]:
            reply = self.client.get("/api/documents", headers=head, params=params)
            self.assertEqual(reply.status_code, 200, reply.text)
            return {d["id"] for d in reply.json()["items"]}

        self.assertEqual(ids(q="15/q"), {mine})  # number and symbol together, as written (ASCII: SQLite lower-cases only ASCII)
        self.assertEqual(ids(q="16/"), {secret})
        self.assertEqual(ids(level="mat"), {secret})
        self.assertEqual(ids(state="uploaded,processing"), set())  # commanders do not see other units' unprocessed files
        self.assertEqual(ids(unit_id="btm"), {mine, secret})  # a parent unit includes the units below it
        self.assertEqual(ids(unit_id="btm.cong_binh"), {mine, secret})
        self.assertEqual(ids(unit_id="btm.hau_can"), set())
        own = self.client.get("/api/documents", headers=self.headers("bo_tham_muu"), params={"state": "uploaded,processing"}).json()
        self.assertEqual({d["id"] for d in own["items"]}, {queued})

    def test_unprocessed_document_is_visible_to_its_uploader_only(self):
        doc_id = self.upload("cong_binh", self.sample()).json()["items"][0]["document"]["id"]
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).status_code, 200)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("bo_tham_muu")).status_code, 404)

    def test_secret_document_is_for_commanders(self):
        reply = self.upload("cong_binh", self.sample(), secret=True)
        doc_id = reply.json()["items"][0]["document"]["id"]
        self.work()
        for who, seen in (("commander", True), ("bo_tham_muu", False), ("admin", False), ("hau_can", False)):
            self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers(who)).status_code, 200 if seen else 404, who)
        hit = self.index.client.scroll(self.collection, limit=1, with_payload=True)[0][0].payload
        self.assertEqual(hit["level"], "mat")

    def test_secrecy_stamp_in_the_file_makes_it_secret(self):
        path = self.sample("stamped.docx", stamp="MẬT")
        doc_id = self.upload("cong_binh", path).json()["items"][0]["document"]["id"]
        self.work()
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("bo_tham_muu")).status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("commander")).json()["level"], "mat")

    def test_unauthenticated_and_unassigned_users(self):
        self.assertEqual(self.client.get("/api/documents").status_code, 401)
        self.assertEqual(self.client.get("/api/documents", headers={"Authorization": "Bearer nope"}).status_code, 401)
        self.assertEqual(self.client.get("/api/documents", headers=self.headers("hau_can")).status_code, 200)
        with self.sessions() as db:
            users.update(db, db.get(type(self.accounts["hau_can"]), self.accounts["hau_can"].id), is_active=False)
            db.commit()
        self.assertEqual(self.client.get("/api/documents", headers=self.headers("hau_can")).status_code, 401)


class LifecycleTest(ApiTestCase):
    def test_content_view_and_download(self):
        doc_id = self.upload_and_process()
        paragraphs = self.client.get(f"/api/documents/{doc_id}/content", headers=self.headers("cong_binh")).json()
        self.assertTrue(any("Điều 1" in p["text"] for p in paragraphs))
        self.assertTrue(all(isinstance(p["pi"], int) for p in paragraphs))
        file = self.client.get(f"/api/documents/{doc_id}/file", headers=self.headers("cong_binh"))
        self.assertEqual(file.status_code, 200)
        self.assertTrue(file.content.startswith(b"PK"))

    def test_manual_metadata_survives_reprocessing_and_reaches_the_index(self):
        doc_id = self.upload_and_process()
        reply = self.client.patch(f"/api/documents/{doc_id}", headers=self.headers("cong_binh"),
                                  json={"title": "Tiêu đề đã sửa", "issued_date": "2026-10-02"})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.client.post(f"/api/documents/{doc_id}/reprocess", headers=self.headers("cong_binh")).status_code, 200)
        self.work()
        detail = self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual((detail["title"], detail["issued_date"]), ("Tiêu đề đã sửa", "2026-10-02"))
        payload = self.index.client.scroll(self.collection, limit=1, with_payload=True)[0][0].payload
        self.assertEqual(payload["title"], "Tiêu đề đã sửa")

    def test_metadata_edit_validation_and_ownership(self):
        doc_id = self.upload_and_process()
        bad = self.client.patch(f"/api/documents/{doc_id}", headers=self.headers("cong_binh"), json={"issued_date": "04/05/2026"})
        self.assertEqual(bad.status_code, 422)
        stranger = self.client.patch(f"/api/documents/{doc_id}", headers=self.headers("bo_tham_muu"), json={"title": "x"})
        self.assertEqual(stranger.status_code, 403)  # can read (parent unit) but is not the uploader or an administrator

    def test_delete_removes_file_index_and_record(self):
        doc_id = self.upload_and_process()
        self.assertEqual(self.client.delete(f"/api/documents/{doc_id}", headers=self.headers("bo_tham_muu")).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).status_code, 204)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).status_code, 404)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(self.index.count(str(doc_id)), 0)

    def test_delete_is_refused_when_the_index_cannot_be_cleaned(self):
        doc_id = self.upload_and_process()
        with mock.patch.object(self.index, "delete_document", side_effect=RuntimeError("down")):
            reply = self.client.delete(f"/api/documents/{doc_id}", headers=self.headers("cong_binh"))
        self.assertEqual(reply.status_code, 503)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).status_code, 200)

    def test_corrupt_file_fails_with_a_reason(self):
        bad = self.tmp / "broken.docx"
        bad.write_bytes(b"PK\x03\x04" + b"not really a zip")
        doc_id = self.upload("cong_binh", bad).json()["items"][0]["document"]["id"]
        self.work()
        detail = self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual(detail["state"], DocumentState.FAILED)
        self.assertTrue(detail["state_detail"])

    def test_index_outage_is_retried_then_fails_the_document(self):
        doc_id = self.upload("cong_binh", self.sample()).json()["items"][0]["document"]["id"]
        with mock.patch.object(indexing, "current", side_effect=ConnectionError("qdrant down")):
            handled = self.work()
        self.assertEqual(handled, config.WORKER_MAX_ATTEMPTS)
        self.assertEqual(self.state_of(doc_id), DocumentState.FAILED)
        # after the outage, "reprocess" brings it back
        self.client.post(f"/api/documents/{doc_id}/reprocess", headers=self.headers("cong_binh"))
        self.work()
        self.assertIn(self.state_of(doc_id), (DocumentState.READY, DocumentState.NEEDS_REVIEW))

    def test_missing_embedding_configuration_fails_with_a_hint(self):
        from app.search import EmbeddingNotConfigured
        doc_id = self.upload("cong_binh", self.sample()).json()["items"][0]["document"]["id"]
        with mock.patch.object(indexing, "current", side_effect=EmbeddingNotConfigured("Chưa cấu hình embedding.")):
            self.work()
        detail = self.client.get(f"/api/documents/{doc_id}", headers=self.headers("cong_binh")).json()
        self.assertEqual(detail["state"], DocumentState.FAILED)
        self.assertIn("Xử lý lại", detail["state_detail"])

    def test_jobs_are_claimed_once(self):
        self.upload("cong_binh", self.sample())
        with self.sessions() as a, self.sessions() as b:
            from app.services import jobs
            first, second = jobs.claim_next(a), jobs.claim_next(b)
        self.assertIsNotNone(first)
        self.assertIsNone(second)


class AdminTest(ApiTestCase):
    def test_admin_area_is_for_admins(self):
        for path in ("/api/admin/users", "/api/admin/settings", "/api/admin/audit-logs"):
            self.assertEqual(self.client.get(path, headers=self.headers("commander")).status_code, 403, path)
            self.assertEqual(self.client.get(path, headers=self.headers("admin")).status_code, 200, path)

    def test_settings_never_expose_secrets_and_external_hosts_need_confirmation(self):
        h = self.headers("admin")
        saved = self.client.put("/api/admin/settings/llm", headers=h, json={"values": {"base_url": "http://10.0.0.5:8000/v1", "api_key": "sk-top-secret"}})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn("sk-top-secret", saved.text)
        self.assertNotIn("sk-top-secret", self.client.get("/api/admin/settings", headers=h).text)
        external = self.client.put("/api/admin/settings/llm", headers=h, json={"values": {"base_url": "https://api.example.com/v1"}})
        self.assertEqual((external.status_code, external.json()["code"], external.json()["hosts"]), (409, "external_endpoint", ["api.example.com"]))
        ok = self.client.put("/api/admin/settings/llm", headers=h,
                             json={"values": {"base_url": "https://api.example.com/v1"}, "confirm_hosts": ["api.example.com"]})
        self.assertEqual(ok.status_code, 200)
        actions = [row["action"] for row in self.client.get("/api/admin/audit-logs", headers=h).json()]
        self.assertIn("settings.save", actions)
        details = " ".join(row["detail"] for row in self.client.get("/api/admin/audit-logs", headers=h).json())
        self.assertNotIn("sk-top-secret", details)

    def test_changing_the_embedding_model_asks_for_a_rebuild(self):
        h = self.headers("admin")
        reply = self.client.put("/api/admin/settings/embedding", headers=h, json={"values": {"provider": "hash", "dim": 64}})
        self.assertTrue(reply.json()["reindex_required"])
        again = self.client.put("/api/admin/settings/embedding", headers=h, json={"values": {"batch_size": 16}})
        self.assertFalse(again.json()["reindex_required"])

    def test_accounts(self):
        h = self.headers("admin")
        body = {"username": "moi", "password": PASSWORD, "full_name": "Người mới", "unit_id": "btm.hau_can", "role": "staff"}
        self.assertEqual(self.client.post("/api/admin/users", headers=h, json=body).status_code, 201)
        self.assertEqual(self.client.post("/api/admin/users", headers=h, json=body).status_code, 409)
        self.assertEqual(self.client.post("/api/admin/users", headers=h, json={**body, "username": "x", "unit_id": "khong-co"}).status_code, 422)
        self.assertEqual(self.client.post("/api/admin/users", headers=h, json={**body, "username": "y", "password": "ngan"}).status_code, 422)
        admin_id = next(u["id"] for u in self.client.get("/api/admin/users", headers=h).json() if u["username"] == "admin")
        locked_out = self.client.patch(f"/api/admin/users/{admin_id}", headers=h, json={"is_active": False})
        self.assertEqual(locked_out.status_code, 409)  # the last administrator cannot be disabled

    def test_reindex_queues_documents(self):
        self.upload_and_process()
        reply = self.client.post("/api/admin/reindex", headers=self.headers("admin"))
        self.assertEqual(reply.json(), {"queued": 1})
        with self.sessions() as db:
            self.assertEqual(db.query(Job).filter(Job.state == "queued").count(), 1)

    def test_login_failures_are_audited_and_generic(self):
        bad = self.client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        unknown = self.client.post("/api/auth/login", json={"username": "ghost", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.json(), unknown.json())  # same answer whether or not the user exists
        rows = self.client.get("/api/admin/audit-logs?action=auth.login_failed", headers=self.headers("admin")).json()
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
