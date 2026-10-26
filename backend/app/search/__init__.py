"""Hybrid (dense + BM25) search over document chunks, backed by Qdrant."""
from .embedders import Embedder, HashEmbedder, OpenAICompatEmbedder
from .factory import EmbeddingNotConfigured, make_embedder
from .rerank import HttpReranker, Reranker, make_reranker
from .sparse import Bm25Config, doc_vector, query_vector
from .store import Hit, QdrantIndex, SearchFilters

__all__ = ["Bm25Config", "Embedder", "EmbeddingNotConfigured", "HashEmbedder", "Hit", "HttpReranker", "OpenAICompatEmbedder",
           "QdrantIndex", "Reranker", "SearchFilters", "doc_vector", "make_embedder", "make_reranker", "query_vector"]
