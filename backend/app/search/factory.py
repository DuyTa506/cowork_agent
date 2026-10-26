"""Builds search components from the admin-editable settings (plain dicts, so this package does not depend on the services)."""
from __future__ import annotations

from app.core import config

from .embedders import Embedder, HashEmbedder, IntramindEmbedder, OpenAICompatEmbedder


class EmbeddingNotConfigured(RuntimeError):
    """No usable embedding model is configured; indexing and semantic search cannot run until an administrator sets one."""


def make_embedder(values: dict) -> Embedder:
    """Builds the embedder described by the ``embedding`` settings section.

    Raises:
        EmbeddingNotConfigured: provider is ``none`` or the settings are incomplete, or ``hash`` is requested in production.
    """
    provider = values.get("provider", "none")
    if provider == "hash":
        if config.APP_ENV == "production":
            raise EmbeddingNotConfigured("Embedding 'hash' chỉ dùng để thử nghiệm, không được bật ở môi trường vận hành.")
        return HashEmbedder(int(values.get("dim") or 256))
    if provider == "openai" and values.get("base_url") and values.get("model") and values.get("dim"):
        return OpenAICompatEmbedder(
            values["base_url"], values["model"], int(values["dim"]), api_key=values.get("api_key", ""),
            query_prefix=values.get("query_prefix", ""), doc_prefix=values.get("doc_prefix", ""),
            batch_size=int(values.get("batch_size") or 32))
    if provider == "intramind" and values.get("base_url") and values.get("dim"):
        return IntramindEmbedder(values["base_url"], int(values["dim"]), api_key=values.get("api_key", ""),
                                 batch_size=int(values.get("batch_size") or 32))
    raise EmbeddingNotConfigured("Chưa cấu hình embedding (Quản trị → Hệ thống → Embedding).")
