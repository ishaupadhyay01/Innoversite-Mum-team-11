from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_ingestion_client
from app.models import Comparison
from app.schemas import ClauseChangeOut, CompareRequest, ComparisonOut
from app.services.compare import compare_versions
from iris_common.errors import NotFoundError
from iris_common.http import ServiceClient

router = APIRouter(prefix="/api/v1/compare", tags=["compare"])


def _out(c: Comparison) -> ComparisonOut:
    return ComparisonOut(
        id=c.id,
        left_version_id=c.left_version_id,
        right_version_id=c.right_version_id,
        left_label=c.left_label,
        right_label=c.right_label,
        summary=c.summary,
        changes=[ClauseChangeOut(**ch) for ch in c.changes],
        created_at=c.created_at,
    )


@router.post(
    "", response_model=ComparisonOut, summary="Compare two document versions or two regulations clause-by-clause"
)
def compare(
    body: CompareRequest, db: Session = Depends(get_db), ingestion: ServiceClient = Depends(get_ingestion_client)
) -> ComparisonOut:
    return _out(compare_versions(db, ingestion, body.left_version_id, body.right_version_id, body.include_unchanged))


@router.get("/{comparison_id}", response_model=ComparisonOut, summary="Fetch a saved comparison")
def get_comparison(comparison_id: uuid.UUID, db: Session = Depends(get_db)) -> ComparisonOut:
    c = db.get(Comparison, comparison_id)
    if c is None:
        raise NotFoundError(f"Comparison {comparison_id} not found")
    return _out(c)
