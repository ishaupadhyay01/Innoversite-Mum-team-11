"""Service-to-service endpoints. Not routed by the public gateway."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ClauseOut, IndexPayload
from app.services.versioning import get_version

router = APIRouter(prefix="/internal/v1", tags=["internal"])


@router.get(
    "/versions/{version_id}/index-payload",
    response_model=IndexPayload,
    summary="Everything search-service needs to index a version",
)
def index_payload(version_id: uuid.UUID, db: Session = Depends(get_db)) -> IndexPayload:
    v = get_version(db, version_id)
    d = v.document
    return IndexPayload(
        document_id=d.id,
        version_id=v.id,
        document_key=d.document_key,
        title=d.title,
        regulator=d.regulator,
        jurisdiction=d.jurisdiction,
        category=d.category,
        version_label=v.version_label,
        status=v.status,
        effective_date=v.effective_date,
        file_name=v.original_filename,
        mime_type=v.mime_type,
        clauses=[ClauseOut.model_validate(c) for c in v.clauses],
    )
