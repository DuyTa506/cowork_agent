"""Admin settings: validation, secret handling, external-endpoint confirmation, embedding identity."""
import json
import unittest

from app.core.errors import ExternalEndpointNotConfirmed, ValidationFailed
from app.models import AppSetting
from app.services import settings
from app.services.settings import endpoints, secrets

from support import memory_session


class SettingsStoreTest(unittest.TestCase):
    def setUp(self):
        self.db = memory_session()

    def test_defaults_come_from_spec_until_saved(self):
        values = settings.load(self.db, "storage")
        self.assertIn("upload_max_mb", values)
        settings.save(self.db, "storage", {"upload_max_mb": 50}, actor="admin")
        self.assertEqual(settings.load(self.db, "storage")["upload_max_mb"], 50)

    def test_rejects_unknown_section_field_and_bad_values(self):
        with self.assertRaises(ValidationFailed):
            settings.save(self.db, "nope", {}, actor="a")
        with self.assertRaises(ValidationFailed):
            settings.save(self.db, "storage", {"bogus": 1}, actor="a")
        for bad in (0, 10_000, "20", 1.5, True):
            with self.assertRaises(ValidationFailed, msg=repr(bad)):
                settings.save(self.db, "storage", {"upload_max_mb": bad}, actor="a")

    def test_url_must_be_http(self):
        with self.assertRaises(ValidationFailed):
            settings.save(self.db, "llm", {"base_url": "ftp://10.0.0.5/v1"}, actor="a")
        settings.save(self.db, "llm", {"base_url": "http://10.0.0.5:8000/v1/"}, actor="a")
        self.assertEqual(settings.load(self.db, "llm")["base_url"], "http://10.0.0.5:8000/v1")

    def test_secret_is_encrypted_at_rest_and_never_public(self):
        settings.save(self.db, "llm", {"api_key": "sk-very-secret"}, actor="a")
        stored = self.db.get(AppSetting, "llm").value["api_key"]
        self.assertNotIn("sk-very-secret", stored)
        self.assertEqual(settings.load(self.db, "llm")["api_key"], "sk-very-secret")
        self.assertNotIn("sk-very-secret", json.dumps(settings.public(self.db)))
        llm = next(s for s in settings.public(self.db)["sections"] if s["key"] == "llm")
        key_field = next(f for f in llm["fields"] if f["name"] == "api_key")
        self.assertEqual(key_field["value"], {"set": True})

    def test_missing_secret_keeps_and_empty_clears(self):
        settings.save(self.db, "llm", {"api_key": "k1"}, actor="a")
        settings.save(self.db, "llm", {"model": "m"}, actor="a")
        self.assertEqual(settings.load(self.db, "llm")["api_key"], "k1")
        settings.save(self.db, "llm", {"api_key": None}, actor="a")
        self.assertEqual(settings.load(self.db, "llm")["api_key"], "k1")
        settings.save(self.db, "llm", {"api_key": ""}, actor="a")
        self.assertEqual(settings.load(self.db, "llm")["api_key"], "")

    def test_undecryptable_secret_is_treated_as_unset(self):
        self.assertEqual(secrets.decrypt("enc:not-a-token"), "")

    def test_external_endpoint_needs_confirmation_once(self):
        payload = {"base_url": "https://api.example.com/v1"}
        with self.assertRaises(ExternalEndpointNotConfirmed) as ctx:
            settings.save(self.db, "llm", payload, actor="a")
        self.assertEqual(ctx.exception.hosts, ["api.example.com"])
        self.assertEqual(settings.load(self.db, "llm")["base_url"], settings.SECTIONS["llm"].field("base_url").default_value())
        result = settings.save(self.db, "llm", payload, actor="a", confirm_hosts=["api.example.com"])
        self.assertEqual(result["new_hosts"], ["api.example.com"])
        settings.save(self.db, "llm", {"model": "x"}, actor="a")  # no new host, no prompt
        settings.save(self.db, "llm", {"base_url": "https://api.example.com/v2"}, actor="a")  # already confirmed

    def test_private_endpoints_need_no_confirmation(self):
        for url in ("http://10.1.2.3:8000/v1", "http://192.168.0.5/v1", "http://localhost:8000/v1", "http://vllm:8000/v1"):
            settings.save(self.db, "llm", {"base_url": url}, actor="a")

    def test_section_without_document_text_skips_confirmation(self):
        # the format-check and storage sections have no endpoints; this guards the flag rather than a url field
        self.assertFalse(settings.SECTIONS["storage"].sends_document_text)

    def test_inconsistent_sections_are_rejected(self):
        with self.assertRaises(ValidationFailed):
            settings.save(self.db, "embedding", {"provider": "openai"}, actor="a")
        with self.assertRaises(ValidationFailed):
            settings.save(self.db, "rerank", {"enabled": True}, actor="a")

    def test_preview_does_not_persist(self):
        merged = settings.preview(self.db, "storage", {"upload_max_mb": 99})
        self.assertEqual(merged["upload_max_mb"], 99)
        self.assertNotEqual(settings.load(self.db, "storage")["upload_max_mb"], 99)

    def test_embedding_fingerprint_tracks_vector_identity_only(self):
        base = {"provider": "openai", "model": "m", "dim": 1024, "doc_prefix": ""}
        self.assertEqual(settings.embedding_fingerprint(base), settings.embedding_fingerprint({**base, "batch_size": 8}))
        self.assertNotEqual(settings.embedding_fingerprint(base), settings.embedding_fingerprint({**base, "dim": 768}))
        self.assertNotEqual(settings.embedding_fingerprint(base), settings.embedding_fingerprint({**base, "model": "n"}))
        self.assertTrue(settings.collection_name(base).endswith(settings.embedding_fingerprint(base)))


class EndpointTest(unittest.TestCase):
    def test_classification(self):
        for host in ("10.0.0.1", "172.16.4.4", "192.168.1.1", "127.0.0.1", "vllm", "llm.lan", ""):
            self.assertTrue(endpoints.is_private_host(host), host)
        for host in ("8.8.8.8", "api.openai.com", "79.117.54.182"):
            self.assertFalse(endpoints.is_private_host(host), host)


if __name__ == "__main__":
    unittest.main()
