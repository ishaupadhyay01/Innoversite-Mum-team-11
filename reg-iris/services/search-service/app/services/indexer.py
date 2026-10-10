"""Consumes ingestion events and keeps the keyword (and semantic) indexes in sync."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.backends.base import ClauseDocument, KeywordBackend, SemanticBackend
from app.models import IndexedVersion
from iris_common.http import ServiceClient
from iris_common.text import canonical_regulator

log = logging.getLogger(__name__)


def build_documents(payload: dict) -> list[ClauseDocument]:
    eff = payload.get("effective_date")
    return [
        ClauseDocument(
            clause_id=c["id"],
            document_id=payload["document_id"],
            version_id=payload["version_id"],
            document_title=payload["title"],
            file_name=payload["file_name"],
            mime_type=payload["mime_type"],
            regulator=payload["regulator"],
            regulator_canonical=canonical_regulator(payload["regulator"]) or "",
            jurisdiction=payload.get("jurisdiction"),
            category=payload.get("category"),
            version_label=payload["version_label"],
            status=payload["status"],
            effective_date=date.fromisoformat(eff) if eff else None,
            clause_ref=c["clause_ref"],
            clause_title=c.get("title"),
            text=c["text"],
            page_start=c["page_start"],
            page_end=c["page_end"],
            anchor=c.get("anchor"),
            ordinal=c["ordinal"],
        )
        for c in payload["clauses"]
    ]


def index_version(
    db: Session, version_id: uuid.UUID, ingestion: ServiceClient, keyword: KeywordBackend, semantic: SemanticBackend
) -> IndexedVersion:
    payload = ingestion.get(f"/internal/v1/versions/{version_id}/index-payload")
    docs = build_documents(payload)
    record = db.get(IndexedVersion, version_id) or IndexedVersion(
        version_id=version_id, document_id=uuid.UUID(payload["document_id"])
    )
    record.status = payload["status"]
    record.clause_count = len(docs)
    record.last_error = None
    keyword.index_clauses(str(version_id), docs)
    record.keyword_indexed = True
    try:
        semantic.index_clauses(str(version_id), docs)
        record.semantic_indexed = not type(semantic).__name__.startswith("Disabled")
    except Exception as exc:  # noqa: BLE001 - semantic is best-effort; keyword search must not depend on it
        record.last_error = f"semantic: {exc}"
        log.warning("semantic_index_failed", extra={"version_id": str(version_id)})
    record.indexed_at = datetime.now(UTC)
    record = db.merge(record)
    db.commit()
    log.info("version_indexed", extra={"version_id": str(version_id), "clauses": len(docs)})
    return record


def apply_status_change(
    db: Session,
    document_id: uuid.UUID,
    active_version_id: uuid.UUID | None,
    keyword: KeywordBackend,
    semantic: SemanticBackend,
) -> None:
    keyword.set_document_status(str(document_id), str(active_version_id) if active_version_id else None)
    semantic.set_document_status(str(document_id), str(active_version_id) if active_version_id else None)
    for rec in db.query(IndexedVersion).filter(IndexedVersion.document_id == document_id):
        rec.status = "ACTIVE" if rec.version_id == active_version_id else "INACTIVE"
    db.commit()
