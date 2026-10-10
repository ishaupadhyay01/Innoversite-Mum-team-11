"""Public API contracts (Pydantic). Changing these is a breaking change for the frontend & search-service."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VersionOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    version_label: str
    status: str = Field(description="ACTIVE | INACTIVE")
    processing_status: str = Field(description="UPLOADED | PROCESSING | READY | FAILED")
    original_filename: str
    mime_type: str
    file_size: int
    sha256: str
    effective_date: date | None
    page_count: int | None
    clause_count: int | None
    quality_warnings: list[str] | None
    error_message: str | None
    uploaded_by: str | None
    uploaded_at: datetime
    processed_at: datetime | None
    activated_at: datetime | None
    file_url: str | None = None


class DocumentOut(ORM):
    id: uuid.UUID
    document_key: str
    title: str
    regulator: str
    jurisdiction: str | None
    category: str | None
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    active_version: VersionOut | None = None


class DocumentDetail(DocumentOut):
    versions: list[VersionOut] = []


class DocumentUpdate(BaseModel):
    title: str | None = None
    regulator: str | None = None
    jurisdiction: str | None = None
    category: str | None = None


class UploadAccepted(BaseModel):
    document: DocumentOut
    version: VersionOut
    message: str = "Upload accepted; processing asynchronously."


class ClauseOut(ORM):
    id: uuid.UUID
    ordinal: int
    clause_ref: str
    title: str | None
    text: str
    page_start: int
    page_end: int
    anchor: str | None


class PageOut(ORM):
    page_number: int
    text: str


class MatchCandidate(BaseModel):
    document_id: uuid.UUID
    document_key: str
    title: str
    regulator: str
    active_version_id: uuid.UUID | None
    active_version_label: str | None
    score: float
    reasons: list[str]


class ExactDuplicate(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    version_label: str


class MatchSuggestionResponse(BaseModel):
    sha256: str
    recommendation: Literal["DUPLICATE", "NEW_VERSION", "NEW_DOCUMENT"]
    exact_duplicate: ExactDuplicate | None
    candidates: list[MatchCandidate]


class InlineOpOut(BaseModel):
    op: str
    text: str


class ClauseChangeOut(BaseModel):
    change: str
    clause_ref: str
    title: str | None
    old_text: str | None
    new_text: str | None
    old_page: int | None
    new_page: int | None
    similarity: float
    inline: list[InlineOpOut] = []


class VersionDiffOut(BaseModel):
    document_id: uuid.UUID
    from_version_id: uuid.UUID
    to_version_id: uuid.UUID
    summary: dict[str, int]
    headline: str
    changes: list[ClauseChangeOut]


class WhatsNewCardOut(ORM):
    id: uuid.UUID
    card_type: str
    document_id: uuid.UUID
    version_id: uuid.UUID
    diff_id: uuid.UUID | None
    regulator: str
    title: str
    effective_date: date | None
    headline: str
    summary: dict[str, int]
    highlights: list[dict[str, Any]]
    created_at: datetime


class AlertOut(ORM):
    id: uuid.UUID
    card_id: uuid.UUID | None
    level: str
    message: str
    created_at: datetime
    read_at: datetime | None


class IngestionStats(BaseModel):
    documents: int
    versions: int
    active_versions: int
    processing: int
    failed: int
    by_regulator: dict[str, int]


class AuditEntryOut(ORM):
    id: int
    entity_type: str
    entity_id: str
    action: str
    actor: str | None
    payload: dict[str, Any]
    created_at: datetime


class IndexPayload(BaseModel):
    """Internal contract consumed by search-service's indexer."""

    document_id: uuid.UUID
    version_id: uuid.UUID
    document_key: str
    title: str
    regulator: str
    jurisdiction: str | None
    category: str | None
    version_label: str
    status: str
    effective_date: date | None
    file_name: str
    mime_type: str
    clauses: list[ClauseOut]
