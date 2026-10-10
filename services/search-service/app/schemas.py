"""Request/response models for the search API."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SearchFiltersIn(BaseModel):
    regulators: list[str] = Field(default_factory=list, max_length=50)
    jurisdictions: list[str] = Field(default_factory=list, max_length=50)
    categories: list[str] = Field(default_factory=list, max_length=50)
    source_types: list[Literal["pdf", "html", "txt"]] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list, max_length=50)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None
    uploaded_from: date | None = None
    uploaded_to: date | None = None

    @model_validator(mode="after")
    def _ranges(self) -> SearchFiltersIn:
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("effective_from must be on or before effective_to")
        if self.uploaded_from and self.uploaded_to and self.uploaded_from > self.uploaded_to:
            raise ValueError("uploaded_from must be on or before uploaded_to")
        return self


class SearchRequest(BaseModel):
    query: str = Field("", max_length=500, description='Keywords; use "double quotes" for exact phrases and -word to exclude')
    filters: SearchFiltersIn = Field(default_factory=SearchFiltersIn)
    scope: Literal["latest", "all", "version"] = Field("latest", description="latest versions only, all versions, or one version")
    version_id: str | None = Field(None, description="Required when scope = version")
    sort: Literal["relevance", "newest", "effective_date", "document_name"] = "relevance"
    match_mode: Literal["smart", "all", "any"] = Field("smart", description="smart: all terms up to 3, then 75%")
    page: int = Field(1, ge=1, le=1000)
    page_size: int = Field(10, ge=1, le=50)
    record_history: bool = True

    @model_validator(mode="after")
    def _scope(self) -> SearchRequest:
        if self.scope == "version" and not self.version_id:
            raise ValueError("version_id is required when scope is 'version'")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"query": "Counterparty LEI", "filters": {"regulators": ["MiFID II"]}, "scope": "latest", "page": 1, "page_size": 10},
                {"query": '"Mandatory Trade Reporting Fields"', "scope": "all"},
            ]
        }
    }


class Segment(BaseModel):
    text: str
    highlight: bool


class Citation(BaseModel):
    regulator: str
    document_name: str
    document_title: str | None
    version: str
    source_type: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None
    section_heading: str | None
    anchor: str | None
    location_label: str
    source_url: str
    viewer_url: str


class DuplicateRef(BaseModel):
    paragraph_id: str
    document_name: str
    version: str
    location_label: str


class SearchHit(BaseModel):
    paragraph_id: str
    score: float | None
    document_id: str
    document_version_id: str
    regulator: str
    jurisdiction: str | None
    category: str | None
    effective_date: date | None
    is_latest: bool
    heading: str | None
    heading_segments: list[Segment]
    text_segments: list[Segment]
    citation: Citation
    identical_text_in: list[DuplicateRef] = Field(default_factory=list)


class FacetBucket(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    query: str
    interpreted: dict[str, Any]
    total: int
    took_ms: float
    es_took_ms: int | None
    page: int
    page_size: int
    total_pages: int
    scope: str
    version_id: str | None
    sort: str
    relaxed: bool
    results: list[SearchHit]
    facets: dict[str, list[FacetBucket]]
    did_you_mean: str | None = None
    notices: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    text: str
    type: Literal["heading", "regulator", "history", "category"]
    detail: str | None = None


class IndexVersionRequest(BaseModel):
    version: dict[str, Any]
    paragraphs: list[dict[str, Any]] = Field(max_length=20000)


class LatestRequest(BaseModel):
    document_id: str
    version_id: str


class ReconcileRequest(BaseModel):
    valid_version_ids: list[str]
