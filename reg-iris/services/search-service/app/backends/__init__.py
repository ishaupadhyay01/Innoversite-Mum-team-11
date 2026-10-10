"""Pluggable search backends.

* ``ElasticsearchBackend`` — production keyword search.
* ``InMemoryBackend``      — tests and ES-less local development (SEARCH_BACKEND=memory).
* ``ChromaSemanticBackend``— optional semantic search (ENABLE_SEMANTIC=true).
"""

from .base import ClauseDocument, KeywordBackend, SearchResult, SemanticBackend

__all__ = ["ClauseDocument", "KeywordBackend", "SearchResult", "SemanticBackend"]
