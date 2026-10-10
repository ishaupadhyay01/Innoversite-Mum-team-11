from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_publisher, get_storage
from app.api.v1.serializers import document_out, version_out
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Document, DocumentVersion, ProcessingStatus, VersionStatus
from app.publisher import EventPublisher
from app.schemas import (
    DocumentDetail,
    DocumentOut,
    DocumentUpdate,
    IngestionStats,
    MatchSuggestionResponse,
    UploadAccepted,
    VersionOut,
)
from app.services import audit
from app.services.documents import DocumentMetadata, UploadedFile, add_version, create_document, suggest_matches
from app.storage import FileStorage
from iris_common.errors import NotFoundError
from iris_common.events import Tasks
from iris_common.pagination import Page, PageParams
from iris_common.text import canonical_regulator

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _read(file: UploadFile) -> UploadedFile:
    return UploadedFile(filename=file.filename or "upload", data=await file.read())


@router.post(
    "/match-suggestions",
    response_model=MatchSuggestionResponse,
    summary="Pre-upload check: exact duplicate + similar existing documents",
)
async def match_suggestions(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    regulator: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MatchSuggestionResponse:
    return suggest_matches(db, await _read(file), DocumentMetadata(title=title, regulator=regulator), settings)


@router.post(
    "",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a NEW regulatory document (creates document + version 1)",
)
async def upload_new_document(
    file: UploadFile = File(...),
    regulator: str = Form(..., examples=["MiFID II"]),
    title: str | None = Form(None),
    jurisdiction: str | None = Form(None, examples=["EU"]),
    category: str | None = Form(None, examples=["Trade reporting"]),
    effective_date: date | None = Form(None),
    version_label: str | None = Form(None, examples=["v1.0"]),
    activate: bool = Form(True, description="Make ACTIVE automatically once processed"),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    publisher: EventPublisher = Depends(get_publisher),
    settings: Settings = Depends(get_settings),
    actor: str | None = Depends(get_actor),
) -> UploadAccepted:
    upload = await _read(file)
    version = create_document(
        db,
        storage,
        settings,
        upload,
        DocumentMetadata(title, regulator, jurisdiction, category),
        version_label=version_label,
        effective_date=effective_date,
        activate=activate,
        actor=actor,
    )
    db.commit()
    publisher.send(Tasks.PROCESS_VERSION, version_id=str(version.id))
    db.refresh(version)
    return UploadAccepted(document=document_out(version.document), version=version_out(version))


@router.post(
    "/{document_id}/versions",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload an UPDATED version of an existing document",
)
async def upload_new_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    effective_date: date | None = Form(None),
    version_label: str | None = Form(None, examples=["v2.0"]),
    activate: bool = Form(True),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    publisher: EventPublisher = Depends(get_publisher),
    settings: Settings = Depends(get_settings),
    actor: str | None = Depends(get_actor),
) -> UploadAccepted:
    version = add_version(
        db,
        storage,
        settings,
        document_id,
        await _read(file),
        version_label=version_label,
        effective_date=effective_date,
        activate=activate,
        actor=actor,
    )
    db.commit()
    publisher.send(Tasks.PROCESS_VERSION, version_id=str(version.id))
    db.refresh(version)
    return UploadAccepted(document=document_out(version.document), version=version_out(version))


@router.get("", response_model=Page[DocumentOut], summary="List documents with filters")
def list_documents(
    params: PageParams = Depends(),
    q: str | None = Query(None, description="Matches title or document key"),
    regulator: str | None = None,
    jurisdiction: str | None = None,
    category: str | None = None,
    has_active: bool | None = None,
    db: Session = Depends(get_db),
) -> Page[DocumentOut]:
    stmt = select(Document)
    if q:
        stmt = stmt.where(or_(Document.title.ilike(f"%{q}%"), Document.document_key.ilike(f"%{q}%")))
    if regulator:
        stmt = stmt.where(Document.regulator_canonical == canonical_regulator(regulator))
    if jurisdiction:
        stmt = stmt.where(Document.jurisdiction == jurisdiction)
    if category:
        stmt = stmt.where(Document.category == category)
    if has_active is not None:
        stmt = stmt.where(
            Document.active_version_id.is_not(None) if has_active else Document.active_version_id.is_(None)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Document.updated_at.desc()).offset(params.offset).limit(params.size)).all()
    return Page.build([document_out(d) for d in rows], total, params)


@router.get("/stats", response_model=IngestionStats, summary="Counts for the dashboard")
def stats(db: Session = Depends(get_db)) -> IngestionStats:
    by_reg = dict(db.execute(select(Document.regulator, func.count()).group_by(Document.regulator)).all())
    count = lambda *w: db.scalar(select(func.count()).select_from(DocumentVersion).where(*w)) or 0
    return IngestionStats(
        documents=db.scalar(select(func.count()).select_from(Document)) or 0,
        versions=count(),
        active_versions=count(DocumentVersion.status == VersionStatus.ACTIVE.value),
        processing=count(
            DocumentVersion.processing_status.in_([ProcessingStatus.UPLOADED.value, ProcessingStatus.PROCESSING.value])
        ),
        failed=count(DocumentVersion.processing_status == ProcessingStatus.FAILED.value),
        by_regulator=by_reg,
    )


@router.get("/{document_id}", response_model=DocumentDetail, summary="Document with full version history")
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentOut:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found")
    return document_out(doc, detail=True)


@router.patch("/{document_id}", response_model=DocumentOut, summary="Edit document metadata")
def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, db: Session = Depends(get_db), actor: str | None = Depends(get_actor)
) -> DocumentOut:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(doc, key, value)
    if "regulator" in changes:
        doc.regulator_canonical = canonical_regulator(doc.regulator) or ""
    audit.record(db, "document", doc.id, "UPDATED", actor, **changes)
    db.commit()
    # TODO(team-ingestion): emit a metadata-changed event so search-service re-indexes filters.
    return document_out(doc)


@router.get("/{document_id}/versions", response_model=list[VersionOut], summary="Version history")
def list_versions(document_id: uuid.UUID, db: Session = Depends(get_db)) -> list[VersionOut]:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found")
    return [version_out(v) for v in reversed(doc.versions)]
