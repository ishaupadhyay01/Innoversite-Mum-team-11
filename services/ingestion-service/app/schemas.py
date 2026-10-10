"""Pydantic response models for the ingestion API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_label: str
    version_seq: int
    parent_version_id: int | None
    file_name: str
    source_type: str
    content_hash: str
    file_size: int
    effective_date: date | None
    uploaded_at: datetime
    origin: str
    is_latest: bool
    status: str
    status_detail: str | None
    title: str | None
    page_count: int | None
    paragraph_count: int
    extractor: str | None
    warnings: list[str]
    metadata_notes: list[str]
    indexed_at: datetime | None
    source_url: str


class DocumentOut(BaseModel):
    id: int
    family_key: str
    title: str
    regulator: str
    jurisdiction: str | None
    category: str | None
    version_count: int
    latest_version: VersionOut | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    versions: list[VersionOut]


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class ParagraphOut(BaseModel):
    paragraph_id: str
    ordinal: int
    heading: str | None
    body: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None
    anchor: str | None
    location: str


class VersionDetail(BaseModel):
    version: VersionOut
    document: DocumentOut
    paragraphs: list[ParagraphOut]


class UploadAccepted(BaseModel):
    job_id: str
    status: str
    status_url: str


class UploadJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_name: str
    status: str
    detail: str | None
    document_id: int | None
    version_id: int | None
    created_at: datetime
    updated_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_id: int
    previous_version_id: int | None
    change_type: str
    change_types: list[str]
    title: str
    summary: str
    regulator: str
    document_name: str
    previous_version_label: str | None
    new_version_label: str
    effective_date: date | None
    diff_stats: dict[str, Any]
    source: str
    is_read: bool
    event_time: datetime
    created_at: datetime


class AlertPage(BaseModel):
    items: list[AlertOut]
    total: int
    unread: int
    page: int
    page_size: int


class AlertReadUpdate(BaseModel):
    is_read: bool = True


class CompareOut(BaseModel):
    base: VersionOut
    target: VersionOut
    same_document: bool
    stats: dict[str, int]
    summary: str
    change_types: list[str]
    rows: list[dict[str, Any]]
    method: str


class ImportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    files_total: int
    files_processed: int
    files_skipped: int
    files_failed: int
    log: list[str]
    errors: list[str]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service: str
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str
    created_at: datetime


class FamilyMatch(BaseModel):
    document_id: int
    title: str
    regulator: str
    latest_version_label: str | None
    suggested_version_label: str
    reason: str
