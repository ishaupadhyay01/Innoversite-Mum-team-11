"""ACTIVE/INACTIVE lifecycle. Exactly one ACTIVE version per document (DB-enforced)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion, ProcessingStatus, VersionStatus
from app.services import audit
from iris_common.errors import ConflictError, NotFoundError


def get_version(db: Session, version_id: uuid.UUID) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise NotFoundError(f"Version {version_id} not found")
    return version


def activate_version(
    db: Session, version_id: uuid.UUID, actor: str | None = None
) -> tuple[DocumentVersion, DocumentVersion | None]:
    """Make ``version_id`` the ACTIVE version. Returns (new_active, previously_active).

    The document row is locked (SELECT … FOR UPDATE) so concurrent activations serialise;
    the partial unique index is the last line of defence.
    """
    version = get_version(db, version_id)
    if version.processing_status != ProcessingStatus.READY.value:
        raise ConflictError("Only fully processed (READY) versions can be activated", code="VERSION_NOT_READY")
    db.execute(select(Document).where(Document.id == version.document_id).with_for_update())
    previous = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == version.document_id, DocumentVersion.status == VersionStatus.ACTIVE.value
        )
    )
    if previous and previous.id == version.id:
        return version, None
    if previous:
        previous.status = VersionStatus.INACTIVE.value
        db.flush()  # release the unique slot before claiming it
    version.status = VersionStatus.ACTIVE.value
    version.activated_at = datetime.now(UTC)
    version.document.active_version_id = version.id
    db.flush()
    audit.record(
        db, "document_version", version.id, "ACTIVATED", actor, previous_version_id=previous.id if previous else None
    )
    return version, previous


def deactivate_version(db: Session, version_id: uuid.UUID, actor: str | None = None) -> DocumentVersion:
    version = get_version(db, version_id)
    if version.status == VersionStatus.ACTIVE.value:
        version.status = VersionStatus.INACTIVE.value
        version.document.active_version_id = None
        db.flush()
        audit.record(db, "document_version", version.id, "DEACTIVATED", actor)
    return version
