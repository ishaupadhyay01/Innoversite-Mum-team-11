from __future__ import annotations

from typing import Any

from app.schemas import SearchFilters
from iris_common.text import canonical_regulator


def es_filter_clauses(f: SearchFilters) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if f.regulator:
        clauses.append({"terms": {"regulator_canonical": [canonical_regulator(r) for r in f.regulator]}})
    if f.jurisdiction:
        clauses.append({"terms": {"jurisdiction": f.jurisdiction}})
    if f.category:
        clauses.append({"terms": {"category": f.category}})
    if f.status != "ALL":
        clauses.append({"term": {"status": f.status}})
    if f.document_id:
        clauses.append({"term": {"document_id": str(f.document_id)}})
    if f.effective_from or f.effective_to:
        rng: dict[str, str] = {}
        if f.effective_from:
            rng["gte"] = f.effective_from.isoformat()
        if f.effective_to:
            rng["lte"] = f.effective_to.isoformat()
        clauses.append({"range": {"effective_date": rng}})
    return clauses


def matches(source: dict[str, Any], f: SearchFilters) -> bool:
    """Same semantics as es_filter_clauses, for the in-memory / Chroma backends."""
    if f.regulator and source["regulator_canonical"] not in {canonical_regulator(r) for r in f.regulator}:
        return False
    if f.jurisdiction and source["jurisdiction"] not in f.jurisdiction:
        return False
    if f.category and source["category"] not in f.category:
        return False
    if f.status != "ALL" and source["status"] != f.status:
        return False
    if f.document_id and source["document_id"] != str(f.document_id):
        return False
    eff = source.get("effective_date")
    if f.effective_from and (not eff or eff < f.effective_from.isoformat()):
        return False
    if f.effective_to and (not eff or eff > f.effective_to.isoformat()):
        return False
    return True
