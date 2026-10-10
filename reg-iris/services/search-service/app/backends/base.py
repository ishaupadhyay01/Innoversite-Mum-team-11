from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.schemas import SearchFilters


@dataclass
class ClauseDocument:
    """One indexed clause. Field names == Elasticsearch mapping (backends/es_mapping.json)."""

    clause_id: str
    document_id: str
    version_id: str
    document_title: str
    file_name: str
    mime_type: str
    regulator: str
    regulator_canonical: str
    jurisdiction: str | None
    category: str | None
    version_label: str
    status: str
    effective_date: date | None
    clause_ref: str
    clause_title: str | None
    text: str
    page_start: int
    page_end: int
    anchor: str | None
    ordinal: int

    def to_source(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["effective_date"] = self.effective_date.isoformat() if self.effective_date else None
        return d


@dataclass
class SearchResult:
    total: int
    hits: list[tuple[dict[str, Any], float, list[str]]] = field(default_factory=list)  # (source, score, highlights)
    facets: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


class KeywordBackend(Protocol):
    def ensure_index(self) -> None: ...
    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None: ...
    def set_document_status(self, document_id: str, active_version_id: str | None) -> None: ...
    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult: ...
    def facets(self) -> dict[str, list[tuple[str, int]]]: ...
    def ping(self) -> bool: ...


class SemanticBackend(Protocol):
    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None: ...
    def set_document_status(self, document_id: str, active_version_id: str | None) -> None: ...
    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult: ...
