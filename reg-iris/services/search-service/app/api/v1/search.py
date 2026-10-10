from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.backends.base import KeywordBackend, SemanticBackend
from app.db import get_db
from app.deps import get_ingestion_client, get_keyword_backend, get_semantic_backend
from app.models import IndexedVersion
from app.schemas import (
    FacetBucket,
    Facets,
    IndexStatusOut,
    SearchFilters,
    SearchMode,
    SearchQuery,
    SearchResponse,
    StatusFilter,
)
from app.services.indexer import index_version
from app.services.search import run_search
from iris_common.errors import NotFoundError
from iris_common.http import ServiceClient

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search regulatory clauses; every hit carries a clickable citation (document + page)",
)
def search(
    q: str = Query(..., min_length=1, max_length=500, examples=["counterparty LEI requirement"]),
    mode: SearchMode = "keyword",
    regulator: list[str] = Query([], description="Repeatable: ?regulator=EMIR&regulator=FCA"),
    jurisdiction: list[str] = Query([]),
    category: list[str] = Query([]),
    status: StatusFilter = "ACTIVE",
    effective_from: date | None = None,
    effective_to: date | None = None,
    document_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    keyword: KeywordBackend = Depends(get_keyword_backend),
    semantic: SemanticBackend = Depends(get_semantic_backend),
) -> SearchResponse:
    filters = SearchFilters(
        regulator=regulator,
        jurisdiction=jurisdiction,
        category=category,
        status=status,
        effective_from=effective_from,
        effective_to=effective_to,
        document_id=document_id,
    )
    return run_search(db, SearchQuery(q=q, mode=mode, filters=filters, page=page, size=size), keyword, semantic)


@router.get("/facets", response_model=Facets, summary="Filter options with counts (for the filter panel)")
def facets(keyword: KeywordBackend = Depends(get_keyword_backend)) -> Facets:
    raw = keyword.facets()
    return Facets(
        **{
            k: [FacetBucket(value=v, count=c) for v, c in raw.get(k, [])]
            for k in ("regulator", "jurisdiction", "category", "status")
        }
    )


@router.get("/index-status", response_model=list[IndexStatusOut], tags=["index admin"])
def index_status(db: Session = Depends(get_db)) -> list[IndexStatusOut]:
    rows = db.query(IndexedVersion).order_by(IndexedVersion.indexed_at.desc()).limit(500).all()
    return [IndexStatusOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/reindex/{version_id}",
    response_model=IndexStatusOut,
    tags=["index admin"],
    summary="Synchronously (re)index one version — recovery tool",
)
def reindex(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    ingestion: ServiceClient = Depends(get_ingestion_client),
    keyword: KeywordBackend = Depends(get_keyword_backend),
    semantic: SemanticBackend = Depends(get_semantic_backend),
) -> IndexStatusOut:
    rec = index_version(db, version_id, ingestion, keyword, semantic)
    if rec is None:
        raise NotFoundError(f"Version {version_id} not found")
    return IndexStatusOut.model_validate(rec, from_attributes=True)
