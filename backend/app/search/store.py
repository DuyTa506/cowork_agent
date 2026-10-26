from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient, models

from app.org.access import Placement, Scope
from app.parsing import ChunkConfig, ParsedDocument, chunk_document

from .embedders import Embedder
from .sparse import Bm25Config, doc_vector, query_vector

DENSE, SPARSE = "dense", "bm25"
_ID_NAMESPACE = uuid.UUID("5b0f6f0e-6f0d-4c7e-9a43-0c3b8f1d2a77")  # fixed: the same chunk always gets the same point id
_KEYWORD_FIELDS = ("unit_path", "level", "doc_id", "doc_type", "part", "symbol", "number")
_TEXT_FIELDS = ("issuing_agency", "title")  # full-text indexes: every word given must appear, accents and case ignored
MODES = ("hybrid", "keyword", "semantic")

@dataclass
class SearchFilters:
    """Optional narrowing on top of the permission scope (which is always applied)."""
    doc_types: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)  # exact, e.g. "QĐ-QK3"
    numbers: list[str] = field(default_factory=list)  # exact, e.g. "15"
    agency: str = ""  # words of the issuing agency's name
    title: str = ""  # words of the trích yếu
    date_from: datetime | None = None
    date_to: datetime | None = None

@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    score: float
    text: str
    context: str
    path: list[str]
    payload: dict[str, Any]

def point_id(doc_id: str, index: int) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"{doc_id}#{index}"))

def scope_filter(scope: Scope, extra: SearchFilters | None = None) -> models.Filter:
    """Permission filter, built into the query itself (never applied to results afterwards): the user's unit must be in the
    chunk's unit_path and the chunk's level one the role may read."""
    must: list[models.Condition] = [
        models.FieldCondition(key="unit_path", match=models.MatchValue(value=scope.unit_id)),
        models.FieldCondition(key="level", match=models.MatchAny(any=sorted(scope.levels))),
    ]
    if extra:
        if extra.doc_types:
            must.append(models.FieldCondition(key="doc_type", match=models.MatchAny(any=extra.doc_types)))
        if extra.doc_ids:
            must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=extra.doc_ids)))
        if extra.symbols:
            must.append(models.FieldCondition(key="symbol", match=models.MatchAny(any=extra.symbols)))
        if extra.numbers:
            must.append(models.FieldCondition(key="number", match=models.MatchAny(any=extra.numbers)))
        if extra.agency:
            must.append(models.FieldCondition(key="issuing_agency", match=models.MatchText(text=extra.agency)))
        if extra.title:
            must.append(models.FieldCondition(key="title", match=models.MatchText(text=extra.title)))
        if extra.date_from or extra.date_to:
            must.append(models.FieldCondition(key="date", range=models.DatetimeRange(gte=extra.date_from, lte=extra.date_to)))
    return models.Filter(must=must)

def _iso(date: str) -> str | None:
    """'2026-05-04' -> RFC 3339 for the datetime index; None for drafts with a blank day/month."""
    if not date:
        return None
    return datetime.fromisoformat(date).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

class QdrantIndex:
    def __init__(self, client: QdrantClient, embedder: Embedder, collection: str = "qk3_chunks",
                 bm25: Bm25Config = Bm25Config(), chunking: ChunkConfig | None = None):
        self.client, self.embedder, self.collection = client, embedder, collection
        self.bm25, self.chunking = bm25, chunking

    @classmethod
    def from_config(cls, embedder: Embedder, collection: str | None = None) -> "QdrantIndex":
        """Index on the Qdrant server from the process configuration; `collection` defaults to the unversioned prefix."""
        from app.core import config
        return cls(QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None), embedder,
                   collection or config.QDRANT_COLLECTION)

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config={DENSE: models.VectorParams(size=self.embedder.dim, distance=models.Distance.COSINE)},
                sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Adds the payload indexes a collection lacks, so a collection made by an older version gains new filters."""
        have = set(self.client.get_collection(self.collection).payload_schema)
        text = models.TextIndexParams(type=models.TextIndexType.TEXT, tokenizer=models.TokenizerType.WORD, lowercase=True,
                                      ascii_folding=True, min_token_len=1)
        wanted: dict[str, Any] = {**{n: models.PayloadSchemaType.KEYWORD for n in _KEYWORD_FIELDS},
                                  "date": models.PayloadSchemaType.DATETIME, **{n: text for n in _TEXT_FIELDS}}
        for name, schema in wanted.items():
            if name not in have:
                self.client.create_payload_index(self.collection, name, schema)

    def index_document(self, doc_id: str, doc: ParsedDocument, placement: Placement, batch: int = 64) -> int:
        """Chunks, embeds and upserts a document; re-indexing replaces it (stale chunks of an older version are removed)."""
        chunks = chunk_document(doc, doc_id, self.chunking)
        meta = doc.metadata
        base = {
            "doc_id": doc_id, "unit_id": placement.unit_id, "unit_path": list(placement.unit_path), "level": placement.level,
            "doc_type": meta.doc_type, "number": meta.number, "symbol": meta.symbol, "title": meta.title,
            "issuing_agency": meta.issuing_agency,
        }
        iso = _iso(meta.date)
        if iso:
            base["date"] = iso
        keep: set[str] = set()
        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            dense = self.embedder.embed_documents([c.embed_text for c in part])
            points = []
            for c, d in zip(part, dense):
                idx, val = doc_vector(c.embed_text, self.bm25)
                pid = point_id(doc_id, c.index)
                keep.add(pid)
                points.append(models.PointStruct(
                    id=pid, vector={DENSE: d, SPARSE: models.SparseVector(indices=idx, values=val)},
                    payload={**base, "chunk_index": c.index, "part": c.part, "path": c.path, "text": c.text,
                             "context": c.context, "pi_first": c.pi_first, "pi_last": c.pi_last}))
            self.client.upsert(self.collection, points=points, wait=True)
        self._delete_stale(doc_id, keep)
        return len(chunks)

    def _doc_filter(self, doc_id: str) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])

    def _delete_stale(self, doc_id: str, keep: set[str]) -> None:
        stale: list[str] = []
        offset = None
        while True:
            pts, offset = self.client.scroll(self.collection, scroll_filter=self._doc_filter(doc_id), limit=256,
                                             offset=offset, with_payload=False, with_vectors=False)
            stale += [str(p.id) for p in pts if str(p.id) not in keep]
            if offset is None:
                break
        if stale:
            self.client.delete(self.collection, points_selector=models.PointIdsList(points=stale), wait=True)

    def delete_document(self, doc_id: str) -> None:
        self.client.delete(self.collection, points_selector=models.FilterSelector(filter=self._doc_filter(doc_id)), wait=True)

    def search(self, query: str, scope: Scope, k: int = 10, filters: SearchFilters | None = None, mode: str = "hybrid",
               fusion: str = "rrf", prefetch_limit: int = 50) -> list[Hit]:
        """Searches the chunks the scope may read. mode: 'hybrid' (dense + BM25, fused by Qdrant), 'keyword' (BM25 only: exact
        words, codes, names) or 'semantic' (dense only: meaning). The permission filter is part of every leg of the query."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if not scope.levels:
            return []
        flt = scope_filter(scope, filters)
        idx, val = query_vector(query)
        sparse = models.SparseVector(indices=idx, values=val)
        if mode == "keyword":
            if not idx:
                return []
            res = self.client.query_points(self.collection, query=sparse, using=SPARSE, query_filter=flt, limit=k, with_payload=True)
        elif mode == "semantic":
            res = self.client.query_points(self.collection, query=self.embedder.embed_query(query), using=DENSE, query_filter=flt,
                                           limit=k, with_payload=True)
        else:
            prefetch = [models.Prefetch(query=self.embedder.embed_query(query), using=DENSE, limit=prefetch_limit, filter=flt)]
            if idx:
                prefetch.append(models.Prefetch(query=sparse, using=SPARSE, limit=prefetch_limit, filter=flt))
            fused = models.RrfQuery(rrf=models.Rrf(k=60)) if fusion == "rrf" else models.FusionQuery(fusion=models.Fusion.DBSF)
            res = self.client.query_points(self.collection, prefetch=prefetch, query=fused, limit=k, with_payload=True)
        return [Hit(f"{p.payload['doc_id']}#{p.payload['chunk_index']}", p.payload["doc_id"], p.score, p.payload["text"],
                    p.payload["context"], p.payload["path"], p.payload) for p in res.points]

    def get_chunks(self, doc_id: str, scope: Scope) -> list[dict[str, Any]]:
        """All chunks of one document in reading order, or [] when it does not exist or the scope may not read it (the two
        cases are indistinguishable on purpose)."""
        base = scope_filter(scope)
        flt = models.Filter(must=[*base.must, models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])
        out: list[dict[str, Any]] = []
        offset = None
        while True:
            pts, offset = self.client.scroll(self.collection, scroll_filter=flt, limit=256, offset=offset,
                                             with_payload=True, with_vectors=False)
            out += [p.payload for p in pts]
            if offset is None:
                break
        return sorted(out, key=lambda p: p["chunk_index"])

    def list_documents(self, scope: Scope, filters: SearchFilters | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """One entry per document (read from its meta chunk), newest first. Documents with no date (drafts) are not listed."""
        base = scope_filter(scope, filters)
        flt = models.Filter(must=[*base.must, models.FieldCondition(key="part", match=models.MatchValue(value="meta"))])
        pts, _ = self.client.scroll(self.collection, scroll_filter=flt, limit=limit, with_payload=True, with_vectors=False,
                                    order_by=models.OrderBy(key="date", direction=models.Direction.DESC))
        return [p.payload for p in pts]

    def count(self, doc_id: str | None = None) -> int:
        return self.client.count(self.collection, count_filter=self._doc_filter(doc_id) if doc_id else None, exact=True).count
