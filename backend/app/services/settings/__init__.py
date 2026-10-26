"""Administrator-editable settings (LLM, embedding, rerank, OCR, format check, storage).

* `spec`       — the catalogue of sections and fields (what can be configured)
* `store`      — persistence, validation, external-endpoint confirmation, embedding fingerprint, cache
* `secrets`    — encryption of API keys at rest
* `endpoints`  — private/external endpoint classification
* `testing`    — "test connection" per section
"""
from . import endpoints, secrets, testing
from .spec import SECTIONS, Field, Section
from .store import (cache, collection_name, confirmed_hosts, embedding_fingerprint, load, preview, public, save,
                    section_of)

__all__ = ["SECTIONS", "Field", "Section", "cache", "collection_name", "confirmed_hosts", "embedding_fingerprint", "endpoints",
           "load", "preview", "public", "save", "section_of", "secrets", "testing"]
