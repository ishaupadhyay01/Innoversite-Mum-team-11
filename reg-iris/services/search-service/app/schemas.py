from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SearchMode = Literal["keyword", "semantic"]
StatusFilter = Literal["ACTIVE", "INACTIVE", "ALL"]


class SearchFilters(BaseModel):
    regulator: list[str] = []
    jurisdiction: list[str] = []
    category: list[str] = []
    status: StatusFilter = "ACTIVE"
    effective_from: date | None = None
    effective_to: date | None = None
    document_id: uuid.UUID | None = None


class SearchQuery(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    mode: SearchMode = "keyword"
    filters: SearchFilters = SearchFilters()
    page: int = 1
    size: int = 10


class Citation(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    document_title: str
    file_name: str
    regulator: str
    version_label: str
    clause_ref: str
    clause_title: str | None
    page: int
    anchor: str | None
    file_url: str = Field(description="Original file; PDFs open at the cited page (#page=N), HTML at the anchor")
    label: str = Field(description="Human-readable citation, e.g. 'MiFID_II_2023_v2.pdf, Paragraph 3, p.1'")


class SearchHit(BaseModel):
    clause_id: uuid.UUID
    score: float
    text: str
    highlights: list[str]
    status: str
    effective_date: date | None
    jurisdiction: str | None
    category: str | None
    citation: Citation


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    total: int
    page: int
    size: int
    took_ms: float
    hits: list[SearchHit]


class FacetBucket(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    regulator: list[FacetBucket]
    jurisdiction: list[FacetBucket]
    category: list[FacetBucket]
    status: list[FacetBucket]


class CompareRequest(BaseModel):
    left_version_id: uuid.UUID
    right_version_id: uuid.UUID
    include_unchanged: bool = False


class InlineOpOut(BaseModel):
    op: str
    text: str


class ClauseChangeOut(BaseModel):
    change: str
    clause_ref: str
    title: str | None
    old_text: str | None
    new_text: str | None
    old_page: int | None
    new_page: int | None
    similarity: float
    inline: list[InlineOpOut] = []


class ComparisonOut(BaseModel):
    id: uuid.UUID
    left_version_id: uuid.UUID
    right_version_id: uuid.UUID
    left_label: str
    right_label: str
    summary: dict[str, int]
    changes: list[ClauseChangeOut]
    created_at: datetime


class IndexStatusOut(BaseModel):
    version_id: uuid.UUID
    document_id: uuid.UUID
    status: str
    clause_count: int
    keyword_indexed: bool
    semantic_indexed: bool
    last_error: str | None
    indexed_at: datetime
