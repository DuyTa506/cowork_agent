"""Access to the search index configured by the administrator.

The embedding model decides what a stored vector means, so the Qdrant collection is named after the embedding fingerprint
(see `settings.embedding_fingerprint`). Changing the model therefore points the application at a new, empty collection;
documents are moved over by re-indexing them (`documents.reindex_all`). Until that finishes, search over the new collection is
partial; run it outside working hours.
"""
from __future__ import annotations

import threading
from typing import Any

from qdrant_client import QdrantClient

from app.core import config
from app.search import Embedder, EmbeddingNotConfigured, QdrantIndex, make_embedder

from . import settings

_lock = threading.Lock()
_cached: tuple[tuple, QdrantIndex] | None = None
_cached_att: tuple[tuple, QdrantIndex] | None = None


class _NoEmbedder:
    """Stand-in used when only the vector store is needed (deleting a document) and no embedding model is configured."""

    dim = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingNotConfigured("Chưa cấu hình embedding (Quản trị → Hệ thống → Embedding).")

    embed_query = embed_documents  # type: ignore[assignment]


def _client() -> QdrantClient:
    """Qdrant connection from the process configuration."""
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def current(values: dict[str, Any] | None = None) -> QdrantIndex:
    """The index for the current embedding settings (collection created on first use). Reused while the settings are unchanged.

    Raises:
        EmbeddingNotConfigured: no usable embedding model is configured.
    """
    global _cached
    values = values if values is not None else settings.cache.get("embedding")
    key = tuple(sorted(values.items()))
    with _lock:
        if _cached is None or _cached[0] != key:
            index = QdrantIndex(_client(), make_embedder(values), settings.collection_name(values))
            index.ensure_collection()
            _cached = (key, index)
        return _cached[1]


def store_only(values: dict[str, Any] | None = None) -> QdrantIndex:
    """The current collection without an embedder: enough to delete or count, never to index or search."""
    values = values if values is not None else settings.cache.get("embedding")
    embedder: Embedder = _NoEmbedder()  # type: ignore[assignment]
    return QdrantIndex(_client(), embedder, settings.collection_name(values))


def attachments(values: dict[str, Any] | None = None) -> QdrantIndex:
    """The index for files attached to chats: same embedding, a collection of its own (`<prefix>_att_<fingerprint>`), so attachments
    are never mixed with, or searchable among, the document store."""
    values = values if values is not None else settings.cache.get("embedding")
    name = f"{config.QDRANT_COLLECTION}_att_{settings.embedding_fingerprint(values)}"
    key = ("att", name, tuple(sorted(values.items())))
    global _cached_att
    with _lock:
        if _cached_att is None or _cached_att[0] != key:
            index = QdrantIndex(_client(), make_embedder(values), name)
            index.ensure_collection()
            _cached_att = (key, index)
        return _cached_att[1]


def attachments_store_only(values: dict[str, Any] | None = None) -> QdrantIndex:
    """The attachments collection without an embedder (for deleting)."""
    values = values if values is not None else settings.cache.get("embedding")
    embedder: Embedder = _NoEmbedder()  # type: ignore[assignment]
    return QdrantIndex(_client(), embedder, f"{config.QDRANT_COLLECTION}_att_{settings.embedding_fingerprint(values)}")


def fingerprint(values: dict[str, Any] | None = None) -> str:
    """Fingerprint of the current embedding settings."""
    return settings.embedding_fingerprint(values if values is not None else settings.cache.get("embedding"))
