"""Document repository, upload, source and version-comparison endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from iris_shared import audit
from iris_shared.config import get_settings
from iris_shared.db import get_session
from iris_shared.models import DocumentVersion, RegulatoryAlert, RegulatoryDocument, UploadJob
from iris_shared.text import normalize_label, sha256_bytes
from iris_shared.web import ApiError

from ..parsers import ParseError
from ..schemas import (
    CompareOut,
    DocumentDetail,
    DocumentOut,
    DocumentPage,
    FamilyMatch,
    ParagraphOut,
    UploadAccepted,
    UploadJobOut,
    VersionDetail,
    VersionOut,
)
from ..services.diffing import compare
from ..services.metadata import family_key_for
from ..services.pipeline import clause_refs, paragraph_id, parse_version
from ..services.storage import UploadRejected, is_within, safe_filename, store_upload, validate_upload
from ..services.uploads import process_upload

router = APIRouter(prefix="/api/documents", tags=["Documents"])

MEDIA_TYPES = {"pdf": "application/pdf", "html": "text/html; charset=utf-8", "txt": "text/plain; charset=utf-8"}


def version_out(v: DocumentVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        document_id=v.document_id,
        version_label=v.version_label,
        version_seq=v.version_seq,
        parent_version_id=v.parent_version_id,
        file_name=v.file_name,
        source_type=v.source_type,
        content_hash=v.content_hash,
        file_size=v.file_size,
        effective_date=v.effective_date,
        uploaded_at=v.uploaded_at,
        origin=v.origin,
        is_latest=v.is_latest,
        status=v.status,
        status_detail=v.status_detail,
        title=v.title,
        page_count=v.page_count,
        paragraph_count=v.paragraph_count,
        extractor=v.extractor,
        warnings=list(v.warnings or []),
        metadata_notes=list(v.metadata_notes or []),
        indexed_at=v.indexed_at,
        source_url=f"/api/documents/{v.document_id}/source?version_id={v.id}",
    )


def document_out(d: RegulatoryDocument) -> DocumentOut:
    versions = list(d.versions)
    latest = next((v for v in versions if v.is_latest), None) or (versions[-1] if versions else None)
    return DocumentOut(
        id=d.id,
        family_key=d.family_key,
        title=d.title,
        regulator=d.regulator,
        jurisdiction=d.jurisdiction,
        category=d.category,
        version_count=len(versions),
        latest_version=version_out(latest) if latest else None,
        created_at=d.created_at,
    )


def _get_document(session: Session, document_id: int) -> RegulatoryDocument:
    doc = session.scalar(
        select(RegulatoryDocument).options(selectinload(RegulatoryDocument.versions)).where(RegulatoryDocument.id == document_id)
    )
    if doc is None:
        raise ApiError(404, "document_not_found", f"Document {document_id} not found")
    return doc


def _get_version(session: Session, version_id: int) -> DocumentVersion:
    v = session.get(DocumentVersion, version_id)
    if v is None:
        raise ApiError(404, "version_not_found", f"Document version {version_id} not found")
    return v


@router.get("", response_model=DocumentPage, summary="List document families with their latest version")
def list_documents(
    q: str | None = Query(None, max_length=200, description="Filter by title, file name or regulator"),
    regulator: list[str] = Query(default=[]),
    jurisdiction: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    uploaded_within_days: int | None = Query(None, ge=1, le=3650, description="Only families with a version uploaded in the last N days"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> DocumentPage:
    stmt = select(RegulatoryDocument).options(selectinload(RegulatoryDocument.versions))
    if q:
        like = f"%{q}%"
        sub = select(DocumentVersion.document_id).where(DocumentVersion.file_name.ilike(like))
        stmt = stmt.where(
            or_(RegulatoryDocument.title.ilike(like), RegulatoryDocument.regulator.ilike(like), RegulatoryDocument.id.in_(sub))
        )
    if regulator:
        stmt = stmt.where(RegulatoryDocument.regulator.in_(regulator))
    if jurisdiction:
        stmt = stmt.where(RegulatoryDocument.jurisdiction.in_(jurisdiction))
    if category:
        stmt = stmt.where(RegulatoryDocument.category.in_(category))
    if uploaded_within_days:
        since = datetime.now(UTC) - timedelta(days=uploaded_within_days)
        stmt = stmt.where(RegulatoryDocument.id.in_(select(DocumentVersion.document_id).where(DocumentVersion.uploaded_at >= since)))
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    docs = session.scalars(
        stmt.order_by(RegulatoryDocument.regulator, RegulatoryDocument.title).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DocumentPage(items=[document_out(d) for d in docs], total=total, page=page, page_size=page_size)


@router.get("/stats", summary="Repository statistics for the dashboard")
def document_stats(session: Session = Depends(get_session)) -> dict[str, object]:
    by_regulator = session.execute(
        select(RegulatoryDocument.regulator, func.count(DocumentVersion.id))
        .join(DocumentVersion, DocumentVersion.document_id == RegulatoryDocument.id)
        .group_by(RegulatoryDocument.regulator)
        .order_by(RegulatoryDocument.regulator)
    ).all()
    status_counts = dict(session.execute(select(DocumentVersion.status, func.count()).group_by(DocumentVersion.status)).all())
    latest = session.scalars(select(DocumentVersion).order_by(DocumentVersion.uploaded_at.desc()).limit(5)).all()
    return {
        "documents": session.scalar(select(func.count(RegulatoryDocument.id))) or 0,
        "versions": session.scalar(select(func.count(DocumentVersion.id))) or 0,
        "regulators": session.scalar(select(func.count(func.distinct(RegulatoryDocument.regulator)))) or 0,
        "paragraphs_recorded": session.scalar(select(func.coalesce(func.sum(DocumentVersion.paragraph_count), 0))) or 0,
        "status_counts": status_counts,
        "versions_by_regulator": [{"regulator": r, "versions": n} for r, n in by_regulator],
        "unread_alerts": session.scalar(select(func.count(RegulatoryAlert.id)).where(RegulatoryAlert.is_read.is_(False))) or 0,
        "latest_versions": [version_out(v).model_dump(mode="json") for v in latest],
    }


@router.get("/match", response_model=list[FamilyMatch], summary="Suggest an existing document family for an upload")
def match_family(
    file_name: str = Query(..., max_length=255),
    regulator: str | None = Query(None, max_length=100),
    session: Session = Depends(get_session),
) -> list[FamilyMatch]:
    key = family_key_for(safe_filename(file_name)).lower()
    docs = session.scalars(select(RegulatoryDocument).options(selectinload(RegulatoryDocument.versions))).all()
    matches: list[FamilyMatch] = []
    for d in docs:
        reason = None
        if d.family_key.lower() == key:
            reason = "same file name stem"
        elif regulator and normalize_label(regulator).lower() == d.regulator.lower():
            reason = "same regulator"
        if reason is None:
            continue
        latest = next((v for v in d.versions if v.is_latest), None)
        matches.append(
            FamilyMatch(
                document_id=d.id,
                title=d.title,
                regulator=d.regulator,
                latest_version_label=latest.version_label if latest else None,
                suggested_version_label=_bump(latest.version_label if latest else None, len(d.versions)),
                reason=reason,
            )
        )
    matches.sort(key=lambda m: (m.reason != "same file name stem", m.title))
    return matches


def _bump(label: str | None, count: int) -> str:
    m = re.match(r"^v?(\d+)(?:\.(\d+))?", label or "")
    if m:
        return f"v{int(m.group(1)) + 1}.0"
    return f"v{count + 1}.0"


@router.post(
    "/upload",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a PDF, HTML or TXT regulatory document (processed asynchronously)",
)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, HTML or TXT file"),
    regulator: str | None = Form(None, max_length=100, description="Required for a new document"),
    jurisdiction: str | None = Form(None, max_length=50),
    category: str | None = Form(None, max_length=100),
    effective_date: date | None = Form(None),
    version_label: str | None = Form(None, max_length=50, pattern=r"^[A-Za-z0-9._ -]+$"),
    document_id: int | None = Form(None, description="Existing document family: upload as a new version"),
    title: str | None = Form(None, max_length=300),
    session: Session = Depends(get_session),
) -> UploadAccepted:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    original_name = file.filename or "upload"
    try:
        source_type = validate_upload(original_name, data, max_bytes)
        clean_name = safe_filename(original_name)
    except UploadRejected as exc:
        raise ApiError(400 if exc.code != "file_too_large" else 413, exc.code, exc.message) from exc

    content_hash = sha256_bytes(data)
    document = None
    if document_id is not None:
        document = _get_document(session, document_id)
        dup = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id, DocumentVersion.content_hash == content_hash)
        )
        if dup:
            raise ApiError(
                409, "duplicate_version", f"This file is identical to {dup.file_name} {dup.version_label}; no new version created"
            )
        if version_label and session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id, DocumentVersion.version_label == version_label.strip()
            )
        ):
            raise ApiError(409, "version_label_exists", f"Version {version_label} already exists for this document")
    else:
        if not regulator or not regulator.strip():
            raise ApiError(422, "regulator_required", "regulator is required when uploading a new document")
        dup = session.scalar(select(DocumentVersion).where(DocumentVersion.content_hash == content_hash))
        if dup:
            raise ApiError(
                409, "duplicate_document", f"This file is identical to {dup.file_name} {dup.version_label} (document {dup.document_id})"
            )

    stored = store_upload(settings.upload_dir, str(document.id) if document else "new", clean_name, data)
    job = UploadJob(
        id=str(uuid.uuid4()),
        file_name=clean_name,
        status="queued",
        document_id=document.id if document else None,
        request={
            "file_name": clean_name,
            "stored_path": str(stored),
            "source_type": source_type,
            "content_hash": content_hash,
            "file_size": len(data),
            "document_id": document.id if document else None,
            "regulator": normalize_label(regulator) if regulator else (document.regulator if document else None),
            "jurisdiction": normalize_label(jurisdiction) or None if jurisdiction else None,
            "category": normalize_label(category) or None if category else None,
            "effective_date": effective_date.isoformat() if effective_date else None,
            "version_label": version_label.strip() if version_label else None,
            "title": title,
        },
    )
    session.add(job)
    audit.record(session, "ingestion", "document.upload_queued", f"Upload queued: {clean_name}", "upload_job", job.id)
    session.commit()
    background.add_task(process_upload, job.id)
    return UploadAccepted(job_id=job.id, status=job.status, status_url=f"/api/documents/uploads/{job.id}")


@router.get("/uploads", response_model=list[UploadJobOut], summary="Recent upload jobs")
def list_uploads(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)) -> list[UploadJobOut]:
    jobs = session.scalars(select(UploadJob).order_by(UploadJob.created_at.desc()).limit(limit)).all()
    return [UploadJobOut.model_validate(j) for j in jobs]


@router.get("/uploads/{job_id}", response_model=UploadJobOut, summary="Upload job status")
def get_upload(job_id: str, session: Session = Depends(get_session)) -> UploadJobOut:
    job = session.get(UploadJob, job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"Upload job {job_id} not found")
    return UploadJobOut.model_validate(job)


@router.get("/compare", response_model=CompareOut, summary="Compare two document versions (deterministic difflib diff)")
def compare_versions(
    base_version_id: int = Query(..., description="Older / previous version"),
    target_version_id: int = Query(..., description="Newer / current version"),
    session: Session = Depends(get_session),
) -> CompareOut:
    base = _get_version(session, base_version_id)
    target = _get_version(session, target_version_id)
    try:
        result = compare(clause_refs(parse_version(base)), clause_refs(parse_version(target)))
    except (ParseError, OSError) as exc:
        raise ApiError(422, "parse_failed", f"Could not re-read a stored version: {exc}") from exc
    return CompareOut(
        base=version_out(base),
        target=version_out(target),
        same_document=base.document_id == target.document_id,
        stats=result.stats,
        summary=result.summary,
        change_types=result.change_types,
        rows=[r.as_dict() for r in result.rows],
        method="difflib.SequenceMatcher over clauses; paired clauses with similarity ≥ 0.55 or identical headings are 'modified'",
    )


@router.get("/versions/{version_id}", response_model=VersionDetail, summary="Version detail with extracted paragraphs")
def get_version(version_id: int, session: Session = Depends(get_session)) -> VersionDetail:
    v = _get_version(session, version_id)
    doc = _get_document(session, v.document_id)
    try:
        parsed = parse_version(v)
    except (ParseError, OSError) as exc:
        raise ApiError(422, "parse_failed", f"Could not re-read stored file: {exc}") from exc
    paragraphs = [
        ParagraphOut(
            paragraph_id=paragraph_id(v.id, ref.ordinal),
            ordinal=ref.ordinal,
            heading=ref.heading,
            body=ref.body,
            page_start=ref.page_start,
            page_end=ref.page_end,
            line_start=ref.line_start,
            line_end=ref.line_end,
            anchor=ref.anchor,
            location=ref.location(),
        )
        for ref in clause_refs(parsed)
    ]
    return VersionDetail(version=version_out(v), document=document_out(doc), paragraphs=paragraphs)


@router.get("/{document_id}", response_model=DocumentDetail, summary="Document family with all versions")
def get_document(document_id: int, session: Session = Depends(get_session)) -> DocumentDetail:
    doc = _get_document(session, document_id)
    base = document_out(doc)
    return DocumentDetail(**base.model_dump(), versions=[version_out(v) for v in doc.versions])


@router.get("/{document_id}/versions", response_model=list[VersionOut], summary="Version history (oldest first)")
def get_versions(document_id: int, session: Session = Depends(get_session)) -> list[VersionOut]:
    return [version_out(v) for v in _get_document(session, document_id).versions]


@router.get(
    "/{document_id}/source",
    summary="Original source file (PDF opens at a page via #page=N; HTML is served sandboxed)",
    response_class=FileResponse,
)
def get_source(
    document_id: int,
    version_id: int | None = Query(None, description="Defaults to the latest version"),
    download: bool = Query(False),
    session: Session = Depends(get_session),
) -> FileResponse:
    doc = _get_document(session, document_id)
    if version_id is not None:
        version = next((v for v in doc.versions if v.id == version_id), None)
        if version is None:
            raise ApiError(404, "version_not_found", f"Version {version_id} does not belong to document {document_id}")
    else:
        version = next((v for v in doc.versions if v.is_latest), None) or (doc.versions[-1] if doc.versions else None)
        if version is None:
            raise ApiError(404, "version_not_found", "Document has no versions")
    settings = get_settings()
    path = Path(version.stored_path)
    if not is_within(path, [settings.regulations_dir, settings.upload_dir]) or not path.exists():
        raise ApiError(404, "source_missing", "Stored source file is not available")
    headers = {
        "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=300",
    }
    if version.source_type == "pdf":
        # Browser PDF viewers are blocked by restrictive CSP; PDFs are not executed by the page.
        headers.pop("Content-Security-Policy")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(version.source_type, "application/octet-stream"),
        filename=version.file_name,
        headers=headers,
        content_disposition_type=disposition,
    )
