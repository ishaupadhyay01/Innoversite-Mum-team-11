from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_publisher, get_storage
from app.api.v1.serializers import version_out
from app.db import get_db
from app.models import AuditLog, DocumentPage
from app.publisher import EventPublisher
from app.schemas import AuditEntryOut, ClauseChangeOut, ClauseOut, PageOut, VersionDiffOut, VersionOut
from app.services.diffing import get_or_create_diff, previous_version
from app.services.versioning import activate_version, deactivate_version, get_version
from app.storage import FileStorage
from iris_common.errors import NotFoundError, ValidationFailedError
from iris_common.events import Tasks

router = APIRouter(prefix="/api/v1/versions", tags=["versions"])


@router.get("/{version_id}", response_model=VersionOut)
def get_version_endpoint(version_id: uuid.UUID, db: Session = Depends(get_db)) -> VersionOut:
    return version_out(get_version(db, version_id))


@router.get("/{version_id}/clauses", response_model=list[ClauseOut])
def list_clauses(version_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ClauseOut]:
    return [ClauseOut.model_validate(c) for c in get_version(db, version_id).clauses]


@router.get("/{version_id}/pages/{page_number}", response_model=PageOut)
def get_page(version_id: uuid.UUID, page_number: int, db: Session = Depends(get_db)) -> PageOut:
    page = db.scalar(
        select(DocumentPage).where(DocumentPage.version_id == version_id, DocumentPage.page_number == page_number)
    )
    if page is None:
        raise NotFoundError(f"Page {page_number} not found")
    return PageOut.model_validate(page)


@router.get(
    "/{version_id}/file", summary="Original file (open inline; append #page=N for PDFs)", response_class=FileResponse
)
def download_file(
    version_id: uuid.UUID, db: Session = Depends(get_db), storage: FileStorage = Depends(get_storage)
) -> FileResponse:
    v = get_version(db, version_id)
    return FileResponse(
        storage.path(v.storage_key),
        media_type=v.mime_type,
        filename=v.original_filename,
        content_disposition_type="inline",
    )


@router.post(
    "/{version_id}/activate",
    response_model=VersionOut,
    summary="Make this the ACTIVE version (previous ACTIVE becomes INACTIVE)",
)
def activate(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
    actor: str | None = Depends(get_actor),
) -> VersionOut:
    version, _ = activate_version(db, version_id, actor)
    db.commit()
    publisher.send(
        Tasks.VERSION_STATUS_CHANGED, document_id=str(version.document_id), active_version_id=str(version.id)
    )
    return version_out(version)


@router.post("/{version_id}/deactivate", response_model=VersionOut)
def deactivate(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
    actor: str | None = Depends(get_actor),
) -> VersionOut:
    version = deactivate_version(db, version_id, actor)
    db.commit()
    publisher.send(Tasks.VERSION_STATUS_CHANGED, document_id=str(version.document_id), active_version_id=None)
    return version_out(version)


@router.get(
    "/{version_id}/diff",
    response_model=VersionDiffOut,
    summary="Compare this version with another version of the same document (default: previous)",
)
def diff(
    version_id: uuid.UUID,
    against: uuid.UUID | None = Query(None),
    include_unchanged: bool = False,
    db: Session = Depends(get_db),
) -> VersionDiffOut:
    new = get_version(db, version_id)
    base_id = against
    if base_id is None:
        prev = previous_version(db, new)
        if prev is None:
            raise ValidationFailedError(
                "This is the first version; nothing to compare against", code="NO_PREVIOUS_VERSION"
            )
        base_id = prev.id
    record, result = get_or_create_diff(db, base_id, version_id)
    db.commit()
    changes = [c for c in record.changes if include_unchanged or c["change"] != "UNCHANGED"]
    return VersionDiffOut(
        document_id=record.document_id,
        from_version_id=record.from_version_id,
        to_version_id=record.to_version_id,
        summary=record.summary,
        headline=result.headline(),
        changes=[ClauseChangeOut(**c) for c in changes],
    )


@router.get("/{version_id}/audit", response_model=list[AuditEntryOut], tags=["audit"])
def audit_trail(version_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditEntryOut]:
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(version_id)).order_by(AuditLog.id)).all()
    return [AuditEntryOut.model_validate(r) for r in rows]
