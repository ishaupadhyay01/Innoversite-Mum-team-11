"""Upload, exact-duplicate detection and pre-upload match suggestions."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Document, DocumentVersion, ProcessingStatus, VersionStatus
from app.parsers import UnsupportedFormatError, detect_format, parse_document
from app.parsers.registry import MIME_TYPES
from app.schemas import ExactDuplicate, MatchCandidate, MatchSuggestionResponse
from app.services import audit
from app.storage import FileStorage
from iris_common.errors import ConflictError, NotFoundError, PayloadTooLargeError, ValidationFailedError
from iris_common.text import (
    canonical_regulator,
    jaccard,
    minhash_signature,
    minhash_similarity,
    sha256_bytes,
    shingles,
    tokens,
)

_VERSION_TOKENS = re.compile(r"^(v\d+(\.\d+)*|\d{4}|final|draft|pdf|html|htm|txt)$")


@dataclass
class UploadedFile:
    filename: str
    data: bytes


@dataclass
class DocumentMetadata:
    title: str | None = None
    regulator: str | None = None
    jurisdiction: str | None = None
    category: str | None = None


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:180] or uuid.uuid4().hex[:8]


def _name_tokens(filename: str) -> set[str]:
    stem = filename.rsplit(".", 1)[0]
    return {t for t in tokens(stem.replace("_", " ")) if not _VERSION_TOKENS.match(t)}


def validate_upload(upload: UploadedFile, settings: Settings) -> str:
    if not upload.data:
        raise ValidationFailedError("Uploaded file is empty", code="EMPTY_FILE")
    if len(upload.data) > settings.max_upload_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File exceeds {settings.max_upload_mb} MB")
    try:
        return detect_format(upload.filename, upload.data)
    except UnsupportedFormatError as exc:
        raise ValidationFailedError(str(exc), code="UNSUPPORTED_FILE") from exc


def find_exact_duplicate(db: Session, sha256: str) -> DocumentVersion | None:
    return db.scalar(select(DocumentVersion).where(DocumentVersion.sha256 == sha256))


def suggest_matches(
    db: Session, upload: UploadedFile, meta: DocumentMetadata, settings: Settings
) -> MatchSuggestionResponse:
    """Score existing documents against an upload *before* it is stored.

    score = 0.5·content(MinHash) + 0.25·filename tokens + 0.15·regulator + 0.10·title
    Scales to a few thousand documents; beyond that move candidate generation to
    Elasticsearch more_like_this (see docs/ARCHITECTURE.md §Scaling).
    """
    fmt = validate_upload(upload, settings)
    sha = sha256_bytes(upload.data)
    dup = find_exact_duplicate(db, sha)
    if dup:
        doc = dup.document
        return MatchSuggestionResponse(
            sha256=sha,
            recommendation="DUPLICATE",
            exact_duplicate=ExactDuplicate(
                document_id=doc.id, version_id=dup.id, title=doc.title, version_label=dup.version_label
            ),
            candidates=[],
        )

    parsed = parse_document(fmt, upload.data)
    sig = minhash_signature(shingles(parsed.full_text))
    name_toks = _name_tokens(upload.filename)
    reg = canonical_regulator(meta.regulator)
    title_toks = set(tokens(meta.title or parsed.title or ""))

    candidates: list[MatchCandidate] = []
    for doc in db.scalars(select(Document)):
        latest = doc.active_version or (doc.versions[-1] if doc.versions else None)
        if latest is None:
            continue
        content = minhash_similarity(sig, latest.fingerprint or [])
        fname = jaccard(name_toks, _name_tokens(latest.original_filename)) if name_toks else 0.0
        reg_score = 1.0 if reg and reg == doc.regulator_canonical else 0.0
        title_score = jaccard(title_toks, set(tokens(doc.title))) if title_toks else 0.0
        score = round(0.5 * content + 0.25 * fname + 0.15 * reg_score + 0.10 * title_score, 4)
        if score < settings.match_min_score:
            continue
        reasons = []
        if content >= 0.3:
            reasons.append(f"{content:.0%} content overlap with {latest.version_label}")
        if fname >= 0.5:
            reasons.append("similar file name")
        if reg_score:
            reasons.append(f"same regulator ({doc.regulator})")
        if title_score >= 0.5:
            reasons.append("similar title")
        candidates.append(
            MatchCandidate(
                document_id=doc.id,
                document_key=doc.document_key,
                title=doc.title,
                regulator=doc.regulator,
                active_version_id=doc.active_version_id,
                active_version_label=doc.active_version.version_label if doc.active_version else None,
                score=score,
                reasons=reasons,
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    candidates = candidates[: settings.match_max_results]
    rec = "NEW_VERSION" if candidates and candidates[0].score >= settings.match_new_version_score else "NEW_DOCUMENT"
    return MatchSuggestionResponse(sha256=sha, recommendation=rec, exact_duplicate=None, candidates=candidates)


def _store_version(
    db: Session,
    storage: FileStorage,
    document: Document,
    upload: UploadedFile,
    fmt: str,
    *,
    version_label: str | None,
    effective_date: date | None,
    activate: bool,
    actor: str | None,
) -> DocumentVersion:
    sha = sha256_bytes(upload.data)
    if dup := find_exact_duplicate(db, sha):
        raise ConflictError(
            "An identical file has already been uploaded",
            code="DUPLICATE_DOCUMENT",
            details={
                "document_id": str(dup.document_id),
                "version_id": str(dup.id),
                "version_label": dup.version_label,
            },
        )
    next_number = (
        db.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id))
        or 0
    ) + 1
    previous = document.active_version
    key = storage.save(upload.data, sha, "html" if fmt == "html" else fmt)
    version = DocumentVersion(
        document=document,
        version_number=next_number,
        version_label=version_label or f"v{next_number}.0",
        parent_version_id=previous.id if previous else None,
        status=VersionStatus.INACTIVE.value,
        processing_status=ProcessingStatus.UPLOADED.value,
        activate_on_ready=activate,
        original_filename=upload.filename,
        storage_key=key,
        mime_type=MIME_TYPES[fmt],
        file_size=len(upload.data),
        sha256=sha,
        effective_date=effective_date,
        uploaded_by=actor,
    )
    db.add(version)
    db.flush()
    audit.record(
        db,
        "document_version",
        version.id,
        "UPLOADED",
        actor,
        document_id=document.id,
        filename=upload.filename,
        sha256=sha,
    )
    return version


def create_document(
    db: Session,
    storage: FileStorage,
    settings: Settings,
    upload: UploadedFile,
    meta: DocumentMetadata,
    *,
    version_label: str | None,
    effective_date: date | None,
    activate: bool,
    actor: str | None,
) -> DocumentVersion:
    fmt = validate_upload(upload, settings)
    if not meta.regulator:
        raise ValidationFailedError("regulator is required", code="MISSING_FIELD")
    title = meta.title or upload.filename.rsplit(".", 1)[0].replace("_", " ")
    key = slugify(f"{meta.regulator}-{title}")
    if db.scalar(select(Document).where(Document.document_key == key)):
        key = f"{key}-{uuid.uuid4().hex[:6]}"
    document = Document(
        document_key=key,
        title=title,
        regulator=meta.regulator,
        regulator_canonical=canonical_regulator(meta.regulator) or "",
        jurisdiction=meta.jurisdiction,
        category=meta.category,
    )
    db.add(document)
    db.flush()
    audit.record(db, "document", document.id, "CREATED", actor, title=title)
    return _store_version(
        db,
        storage,
        document,
        upload,
        fmt,
        version_label=version_label,
        effective_date=effective_date,
        activate=activate,
        actor=actor,
    )


def add_version(
    db: Session,
    storage: FileStorage,
    settings: Settings,
    document_id: uuid.UUID,
    upload: UploadedFile,
    *,
    version_label: str | None,
    effective_date: date | None,
    activate: bool,
    actor: str | None,
) -> DocumentVersion:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    fmt = validate_upload(upload, settings)
    return _store_version(
        db,
        storage,
        document,
        upload,
        fmt,
        version_label=version_label,
        effective_date=effective_date,
        activate=activate,
        actor=actor,
    )
