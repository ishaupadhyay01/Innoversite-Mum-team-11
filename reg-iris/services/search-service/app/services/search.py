from __future__ import annotations

import html
import time
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.backends.base import KeywordBackend, SemanticBackend
from app.models import SearchQueryLog
from app.schemas import Citation, SearchHit, SearchQuery, SearchResponse


def citation_for(src: dict) -> Citation:
    page = int(src["page_start"])
    is_html = src.get("mime_type") == "text/html"
    fragment = f"#{src['anchor']}" if is_html and src.get("anchor") else f"#page={page}"
    loc = "" if is_html else f", p.{page}"
    return Citation(
        document_id=uuid.UUID(src["document_id"]),
        version_id=uuid.UUID(src["version_id"]),
        document_title=src["document_title"],
        file_name=src["file_name"],
        regulator=src["regulator"],
        version_label=src["version_label"],
        clause_ref=src["clause_ref"],
        clause_title=src.get("clause_title"),
        page=page,
        anchor=src.get("anchor"),
        file_url=f"/api/v1/versions/{src['version_id']}/file{fragment}",
        label=f"{src['file_name']} ({src['version_label']}), {src['clause_ref']}{loc}",
    )


def run_search(db: Session, query: SearchQuery, keyword: KeywordBackend, semantic: SemanticBackend) -> SearchResponse:
    started = time.perf_counter()
    backend = semantic if query.mode == "semantic" else keyword
    offset = (query.page - 1) * query.size
    result = backend.search(query.q, query.filters, offset, query.size)
    took = round((time.perf_counter() - started) * 1000, 1)
    hits = [
        SearchHit(
            clause_id=uuid.UUID(src["clause_id"]),
            score=round(score, 4),
            text=src["text"],
            highlights=hl or [html.escape(src["text"][:220])],
            status=src["status"],
            effective_date=date.fromisoformat(src["effective_date"]) if src.get("effective_date") else None,
            jurisdiction=src.get("jurisdiction"),
            category=src.get("category"),
            citation=citation_for(src),
        )
        for src, score, hl in result.hits
    ]
    db.add(
        SearchQueryLog(
            query=query.q,
            mode=query.mode,
            filters=query.filters.model_dump(mode="json"),
            result_count=result.total,
            took_ms=took,
        )
    )
    db.commit()
    return SearchResponse(
        query=query.q, mode=query.mode, total=result.total, page=query.page, size=query.size, took_ms=took, hits=hits
    )
