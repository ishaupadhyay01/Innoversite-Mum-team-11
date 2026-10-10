"""Process-wide singletons (overridable in tests via app.dependency_overrides)."""

from __future__ import annotations

from functools import lru_cache

from app.backends.base import KeywordBackend, SemanticBackend
from app.backends.semantic import DisabledSemanticBackend
from app.config import get_settings
from iris_common.http import ServiceClient


@lru_cache
def get_keyword_backend() -> KeywordBackend:
    s = get_settings()
    if s.search_backend == "memory":
        from app.backends.memory import InMemoryBackend

        return InMemoryBackend()
    from app.backends.elastic import ElasticsearchBackend

    return ElasticsearchBackend(s.elasticsearch_url, s.clause_index_alias)


@lru_cache
def get_semantic_backend() -> SemanticBackend:
    s = get_settings()
    if not s.enable_semantic:
        return DisabledSemanticBackend()
    from app.backends.semantic import ChromaSemanticBackend

    return ChromaSemanticBackend(s.chroma_url, s.chroma_collection, s.embedding_model)


@lru_cache
def get_ingestion_client() -> ServiceClient:
    s = get_settings()
    return ServiceClient(s.ingestion_url, token=s.api_token)
