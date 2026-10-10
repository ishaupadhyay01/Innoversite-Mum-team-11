"""Optional semantic search with ChromaDB + sentence-transformers (all-MiniLM-L6-v2).

Enabled with ENABLE_SEMANTIC=true and the `semantic` docker-compose profile.
TODO(team-search): hybrid ranking (RRF of keyword + semantic) and a grounded Q&A endpoint.
"""

from __future__ import annotations

import html
import logging
from typing import Any

from app.backends.base import ClauseDocument, SearchResult
from app.backends.filters import matches
from app.schemas import SearchFilters
from iris_common.errors import FeatureDisabledError

log = logging.getLogger(__name__)


class DisabledSemanticBackend:
    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None:
        return None

    def set_document_status(self, document_id: str, active_version_id: str | None) -> None:
        return None

    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult:
        raise FeatureDisabledError(
            "Semantic search is disabled. Set ENABLE_SEMANTIC=true and start the " "'semantic' compose profile.",
            code="SEMANTIC_DISABLED",
        )


class ChromaSemanticBackend:
    def __init__(self, url: str, collection: str, model_name: str) -> None:
        import chromadb  # lazy: optional dependency
        from sentence_transformers import SentenceTransformer

        host, _, port = url.removeprefix("http://").partition(":")
        self.client = chromadb.HttpClient(host=host, port=int(port or 8000))
        self.collection = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        self.model = SentenceTransformer(model_name)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None:
        self.collection.delete(where={"version_id": version_id})
        if not docs:
            return
        metas: list[dict[str, Any]] = [
            {k: v for k, v in d.to_source().items() if k != "text" and v is not None} for d in docs
        ]
        self.collection.add(
            ids=[d.clause_id for d in docs],
            embeddings=self._embed([f"{d.clause_title or ''}. {d.text}" for d in docs]),
            documents=[d.text for d in docs],
            metadatas=metas,
        )  # type: ignore[arg-type]

    def set_document_status(self, document_id: str, active_version_id: str | None) -> None:
        got = self.collection.get(where={"document_id": document_id}, include=["metadatas"])
        metas = [
            {**m, "status": "ACTIVE" if m["version_id"] == active_version_id else "INACTIVE"}
            for m in got["metadatas"] or []
        ]
        if got["ids"]:
            self.collection.update(ids=got["ids"], metadatas=metas)  # type: ignore[arg-type]

    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult:
        # Over-fetch then filter in Python so filter semantics match the keyword backend exactly.
        res = self.collection.query(
            query_embeddings=self._embed([q]),
            n_results=min(200, offset + size * 5),
            include=["metadatas", "documents", "distances"],
        )
        rows = []
        for meta, text, dist in zip(res["metadatas"][0], res["documents"][0], res["distances"][0], strict=True):  # type: ignore[index]
            source = {**meta, "text": text}
            source.setdefault("jurisdiction", None)
            source.setdefault("category", None)
            source.setdefault("effective_date", None)
            if matches(source, filters):
                rows.append((source, round(1 - float(dist), 4), [html.escape(text[:300])]))
        return SearchResult(total=len(rows), hits=rows[offset : offset + size])
