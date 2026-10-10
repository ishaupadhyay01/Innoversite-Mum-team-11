"""Ingestion pipeline: parse -> persist version & paragraph metadata -> index -> diff -> alert.

Used both by the initial dataset import (seeding) and by user uploads, so
both paths produce identical records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iris_shared import audit
from iris_shared.models import DocumentParagraph, DocumentVersion, RegulatoryAlert, RegulatoryDocument
from iris_shared.text import normalize_inline, sha256_text

from ..parsers import ParsedDocument, parse_document
from . import search_client
from .diffing import ClauseRef, DiffResult, compare

logger = logging.getLogger("ingestion.pipeline")
SERVICE = "ingestion"


@dataclass
class VersionInput:
    file_name: str
    stored_path: Path
    source_type: str
    content_hash: str
    file_size: int
    version_label: str
    effective_date: date | None
    uploaded_at: datetime
    origin: str  # seed | upload
    source_metadata_id: int | None = None
    parent_version_id: int | None = None
    metadata_notes: list[str] | None = None


@dataclass
class AlertPolicy:
    source: str  # initial_import | upload
    is_read: bool
    event_time: datetime


def paragraph_id(version_id: int, ordinal: int) -> str:
    return f"v{version_id}-p{ordinal:04d}"


@lru_cache(maxsize=64)
def _cached_parse(path: str, content_hash: str, source_type: str) -> ParsedDocument:
    return parse_document(Path(path), source_type)


def parse_version(version: DocumentVersion) -> ParsedDocument:
    return _cached_parse(version.stored_path, version.content_hash, version.source_type)


def clause_refs(parsed: ParsedDocument) -> list[ClauseRef]:
    return [ClauseRef(c.ordinal, c.heading, c.body, c.page_start, c.page_end, c.line_start, c.line_end, c.anchor) for c in parsed.clauses]


def next_version_seq(session: Session, document_id: int) -> int:
    current = session.scalar(select(func.max(DocumentVersion.version_seq)).where(DocumentVersion.document_id == document_id))
    return (current or 0) + 1


def latest_version(session: Session, document_id: int) -> DocumentVersion | None:
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.status == "indexed")
        .order_by(DocumentVersion.version_seq.desc())
        .limit(1)
    )


def build_es_docs(document: RegulatoryDocument, version: DocumentVersion, parsed: ParsedDocument, is_latest: bool) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    docs = []
    for c in parsed.clauses:
        docs.append(
            {
                "paragraph_id": paragraph_id(version.id, c.ordinal),
                "document_id": str(document.id),
                "document_version_id": str(version.id),
                "document_name": version.file_name,
                "document_title": version.title or document.title,
                "regulator": document.regulator,
                "jurisdiction": document.jurisdiction,
                "category": document.category,
                "version": version.version_label,
                "source_type": version.source_type,
                "effective_date": version.effective_date.isoformat() if version.effective_date else None,
                "uploaded_at": version.uploaded_at.isoformat(),
                "is_latest": is_latest,
                "ordinal": c.ordinal,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "anchor": c.anchor,
                "section_heading": c.heading,
                "heading_suggest": c.heading,
                "content": c.search_body,
                "content_hash": sha256_text(normalize_inline(c.text).lower()),
                "char_count": len(c.text),
                "indexed_at": now,
            }
        )
    return docs


def _persist_paragraphs(session: Session, version: DocumentVersion, es_docs: list[dict[str, Any]]) -> None:
    for existing in list(version.paragraphs):
        session.delete(existing)
    session.flush()
    for d in es_docs:
        session.add(
            DocumentParagraph(
                id=d["paragraph_id"],
                version_id=version.id,
                ordinal=d["ordinal"],
                section_heading=(d["section_heading"] or None) and d["section_heading"][:500],
                page_start=d["page_start"],
                page_end=d["page_end"],
                line_start=d["line_start"],
                line_end=d["line_end"],
                anchor=d["anchor"],
                content_hash=d["content_hash"],
                char_count=d["char_count"],
            )
        )


def index_version(session: Session, document: RegulatoryDocument, version: DocumentVersion, parsed: ParsedDocument) -> None:
    """(Re)index a version. Marks it latest if it has the highest sequence number in its family."""
    newest = session.scalar(
        select(func.max(DocumentVersion.version_seq)).where(
            DocumentVersion.document_id == document.id,
            (DocumentVersion.status == "indexed") | (DocumentVersion.id == version.id),
        )
    )
    will_be_latest = version.version_seq >= (newest or 0)
    es_docs = build_es_docs(document, version, parsed, will_be_latest)
    _persist_paragraphs(session, version, es_docs)
    meta = {
        "document_id": str(document.id),
        "document_version_id": str(version.id),
        "document_name": version.file_name,
    }
    result = search_client.index_version(meta, es_docs)
    if result.get("errors"):
        raise search_client.SearchServiceError(f"{len(result['errors'])} paragraph(s) failed to index: {result['errors'][:3]}")
    if will_be_latest:
        search_client.set_latest(document.id, version.id)
        for other in document.versions:
            other.is_latest = other.id == version.id
        version.is_latest = True
    version.paragraph_count = len(es_docs)
    version.indexed_at = datetime.now(UTC)
    version.status = "indexed"
    version.status_detail = None


def create_version(session: Session, document: RegulatoryDocument, data: VersionInput, parsed: ParsedDocument) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document.id,
        version_label=data.version_label,
        version_seq=next_version_seq(session, document.id),
        parent_version_id=data.parent_version_id,
        file_name=data.file_name,
        stored_path=str(data.stored_path),
        source_type=data.source_type,
        content_hash=data.content_hash,
        file_size=data.file_size,
        effective_date=data.effective_date,
        uploaded_at=data.uploaded_at,
        origin=data.origin,
        source_metadata_id=data.source_metadata_id,
        is_latest=False,
        status="processing",
        title=parsed.title,
        page_count=parsed.page_count,
        paragraph_count=0,
        extractor=parsed.extractor,
        warnings=list(parsed.warnings),
        metadata_notes=list(data.metadata_notes or []),
    )
    session.add(version)
    session.flush()
    document.versions  # noqa: B018 - load relationship before mutation
    return version


def diff_versions(session: Session, old: DocumentVersion, new: DocumentVersion) -> DiffResult:
    return compare(clause_refs(parse_version(old)), clause_refs(parse_version(new)))


def create_alert(
    session: Session,
    document: RegulatoryDocument,
    version: DocumentVersion,
    policy: AlertPolicy,
) -> RegulatoryAlert:
    previous = session.get(DocumentVersion, version.parent_version_id) if version.parent_version_id else None
    if previous is not None:
        diff = diff_versions(session, previous, version)
        change_type = "New Version"
        change_types = ["New Version", *diff.change_types]
        summary = diff.summary
        stats = diff.stats
        title = f"{document.regulator}: {version.file_name} ({previous.version_label} → {version.version_label})"
    else:
        change_type = "New Document"
        change_types = ["New Document"]
        pages = f", {version.page_count} page(s)" if version.page_count else ""
        summary = f"New document indexed: {version.paragraph_count} clause(s){pages}."
        stats = {"new_clauses": version.paragraph_count}
        title = f"{document.regulator}: {version.file_name} ({version.version_label})"
    existing = session.scalar(select(RegulatoryAlert).where(RegulatoryAlert.version_id == version.id))
    if existing is not None:
        return existing
    alert = RegulatoryAlert(
        document_id=document.id,
        version_id=version.id,
        previous_version_id=previous.id if previous else None,
        change_type=change_type,
        change_types=change_types,
        title=title[:400],
        summary=summary,
        regulator=document.regulator,
        document_name=version.file_name,
        previous_version_label=previous.version_label if previous else None,
        new_version_label=version.version_label,
        effective_date=version.effective_date,
        diff_stats=stats,
        source=policy.source,
        is_read=policy.is_read,
        event_time=policy.event_time,
    )
    session.add(alert)
    audit.record(
        session,
        SERVICE,
        "alert.created",
        f"What's New alert: {title}",
        "alert",
        version.id,
        {"change_types": change_types, "source": policy.source},
    )
    return alert


def ingest(
    session: Session,
    document: RegulatoryDocument,
    data: VersionInput,
    policy: AlertPolicy,
) -> DocumentVersion:
    """Full pipeline for one new version. Raises ParseError / SearchServiceError on failure;
    the caller decides how to record the failure."""
    parsed = parse_document(data.stored_path, data.source_type)
    version = create_version(session, document, data, parsed)
    index_version(session, document, version, parsed)
    session.flush()
    create_alert(session, document, version, policy)
    audit.record(
        session,
        SERVICE,
        "document.indexed",
        f"Indexed {version.file_name} {version.version_label} ({version.paragraph_count} clauses)",
        "document_version",
        version.id,
        {"origin": data.origin, "warnings": parsed.warnings},
    )
    return version
