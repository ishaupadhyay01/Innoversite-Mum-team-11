"""Public search API and internal indexing API."""

from __future__ import annotations

from elasticsearch import ApiError as EsApiError
from elasticsearch import TransportError
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from iris_shared.db import get_session
from iris_shared.web import ApiError, require_internal_token

from .. import history
from ..indexing.indexer import Indexer
from ..schemas import IndexVersionRequest, LatestRequest, ReconcileRequest, SearchRequest, SearchResponse, Suggestion
from ..search.service import SearchService

public = APIRouter(prefix="/api/search", tags=["Search"])
internal = APIRouter(prefix="/internal", tags=["Internal (service-to-service)"], dependencies=[Depends(require_internal_token)])


def get_service(request: Request) -> SearchService:
    return request.app.state.search_service


def get_indexer(request: Request) -> Indexer:
    return request.app.state.indexer


def _es_unavailable(exc: Exception) -> ApiError:
    return ApiError(503, "search_unavailable", f"Elasticsearch is not available: {type(exc).__name__}")


@public.post("", response_model=SearchResponse, summary="Keyword (BM25) search over indexed regulatory paragraphs")
def search(
    body: SearchRequest,
    background: BackgroundTasks,
    service: SearchService = Depends(get_service),
) -> SearchResponse:
    try:
        response = service.search(body)
    except ValueError as exc:
        raise ApiError(422, "invalid_search", str(exc)) from exc
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc
    if body.record_history:
        background.add_task(
            history.record_search,
            body.query,
            body.filters.model_dump(mode="json", exclude_defaults=True),
            body.scope,
            response.total,
            response.took_ms,
            response.relaxed,
        )
    return response


@public.get("/suggestions", response_model=list[Suggestion], summary="Search-as-you-type suggestions (headings, regulators, history)")
def suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    service: SearchService = Depends(get_service),
    session: Session = Depends(get_session),
) -> list[Suggestion]:
    out: list[Suggestion] = []
    prefix = q.strip().lower()
    try:
        facets = service.facet_values()
        for name, kind in (("regulator", "regulator"), ("category", "category")):
            for bucket in facets.get(name, []):
                if str(bucket["value"]).lower().startswith(prefix):
                    out.append(Suggestion(text=str(bucket["value"]), type=kind, detail=f"{bucket['count']} paragraphs"))
        for item in service.suggestions(q, limit):
            out.append(Suggestion(text=item["text"], type="heading", detail=item.get("detail")))
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc
    for past in history.history_suggestions(session, q):
        if all(s.text.lower() != past for s in out):
            out.append(Suggestion(text=past, type="history", detail="recent search"))
    return out[:limit]


@public.get("/filters", summary="Available filter values (from indexed metadata)")
def filters(service: SearchService = Depends(get_service)) -> dict[str, object]:
    try:
        return service.facet_values()
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc


@public.get("/paragraphs/{paragraph_id}", summary="Exact source paragraph with neighbouring context")
def paragraph(paragraph_id: str, context: int = Query(1, ge=0, le=5), service: SearchService = Depends(get_service)) -> dict[str, object]:
    try:
        result = service.get_paragraph(paragraph_id, context)
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc
    if result is None:
        raise ApiError(404, "paragraph_not_found", f"Paragraph {paragraph_id} is not indexed")
    return result


@public.get("/versions/{version_id}/paragraphs", summary="All indexed paragraphs of one document version")
def version_paragraphs(version_id: str, service: SearchService = Depends(get_service)) -> dict[str, object]:
    try:
        items = service.version_paragraphs(version_id)
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc
    return {"version_id": version_id, "count": len(items), "paragraphs": items}


@public.get("/analytics", summary="Search usage analytics (query history and response times)")
def analytics(days: int = Query(14, ge=1, le=365), session: Session = Depends(get_session)) -> dict[str, object]:
    data = history.analytics(session, days)
    data["recent"] = history.recent_queries(session)
    return data


# ----------------------------------------------------------------------------- internal


@internal.post("/index", summary="Replace all paragraphs of one document version")
def index_version(body: IndexVersionRequest, indexer: Indexer = Depends(get_indexer)) -> dict[str, object]:
    version_id = str(body.version.get("document_version_id") or "")
    if not version_id:
        raise ApiError(422, "missing_version", "version.document_version_id is required")
    for p in body.paragraphs:
        if str(p.get("document_version_id")) != version_id:
            raise ApiError(422, "version_mismatch", f"paragraph {p.get('paragraph_id')} belongs to another version")
    try:
        return indexer.index_version(version_id, body.paragraphs)
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc


@internal.post("/latest", summary="Mark one version as the latest of its document")
def set_latest(body: LatestRequest, indexer: Indexer = Depends(get_indexer)) -> dict[str, int]:
    return indexer.set_latest(body.document_id, body.version_id)


@internal.get("/versions/{version_id}/count")
def version_count(version_id: str, indexer: Indexer = Depends(get_indexer)) -> dict[str, int]:
    return {"count": indexer.version_count(version_id)}


@internal.delete("/versions/{version_id}")
def delete_version(version_id: str, indexer: Indexer = Depends(get_indexer)) -> dict[str, int]:
    return {"deleted": indexer.delete_version(version_id)}


@internal.post("/reconcile", summary="Delete paragraphs whose version no longer exists")
def reconcile(body: ReconcileRequest, indexer: Indexer = Depends(get_indexer)) -> dict[str, int]:
    return {"deleted": indexer.reconcile(body.valid_version_ids)}


@internal.post("/reset", summary="Drop and recreate the index")
def reset(indexer: Indexer = Depends(get_indexer)) -> dict[str, str]:
    indexer.reset()
    return {"status": "reset", "index": indexer.concrete_name}


@internal.get("/stats", summary="Index statistics")
def stats(indexer: Indexer = Depends(get_indexer)) -> dict[str, object]:
    try:
        return indexer.stats()
    except (TransportError, EsApiError) as exc:
        raise _es_unavailable(exc) from exc
