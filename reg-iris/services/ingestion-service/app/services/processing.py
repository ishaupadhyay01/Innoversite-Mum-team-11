"""Asynchronous processing pipeline for an uploaded version.

UPLOADED → PROCESSING → parse → pages/clauses → fingerprint → READY
        → (activate if requested) → What's New card + alert → notify search-service
Any exception → FAILED with error_message (upload is kept for re-processing).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Clause, DocumentPage, ProcessingStatus, VersionStatus
from app.parsers import detect_format, parse_document
from app.publisher import EventPublisher
from app.services import audit
from app.services.diffing import generate_whats_new
from app.services.versioning import activate_version, get_version
from app.storage import FileStorage
from iris_common.events import Tasks
from iris_common.text import minhash_signature, sha256_bytes, shingles

log = logging.getLogger(__name__)


def process_version(db: Session, version_id: uuid.UUID, storage: FileStorage, publisher: EventPublisher) -> None:
    version = get_version(db, version_id)
    if version.processing_status == ProcessingStatus.READY.value:
        log.info("already_processed", extra={"version_id": str(version_id)})
        return
    version.processing_status = ProcessingStatus.PROCESSING.value
    db.commit()

    try:
        data = storage.read(version.storage_key)
        parsed = parse_document(detect_format(version.original_filename, data), data)
        version.pages = [DocumentPage(page_number=p.page_number, text=p.text) for p in parsed.pages]
        version.clauses = [
            Clause(
                ordinal=c.ordinal,
                clause_ref=c.clause_ref,
                title=c.title,
                text=c.text,
                page_start=c.page_start,
                page_end=c.page_end,
                anchor=c.anchor,
                text_hash=sha256_bytes(c.text.encode()),
            )
            for c in parsed.clauses
        ]
        version.page_count = len(parsed.pages)
        version.clause_count = len(parsed.clauses)
        version.fingerprint = minhash_signature(shingles(parsed.full_text))
        version.quality_warnings = parsed.warnings or None
        version.processing_status = ProcessingStatus.READY.value
        version.processed_at = datetime.now(UTC)
        db.flush()

        status_changed = False
        if version.activate_on_ready:
            _, _previous = activate_version(db, version.id)
            status_changed = True
        generate_whats_new(db, version)
        audit.record(db, "document_version", version.id, "PROCESSED", None, clauses=version.clause_count)
        db.commit()
    except Exception as exc:
        db.rollback()
        version = get_version(db, version_id)
        version.processing_status = ProcessingStatus.FAILED.value
        version.error_message = f"{exc.__class__.__name__}: {exc}"[:2000]
        audit.record(db, "document_version", version.id, "PROCESSING_FAILED", None, error=version.error_message)
        db.commit()
        log.exception("processing_failed", extra={"version_id": str(version_id)})
        return

    # Notify search-service only after the commit, so it reads committed data.
    publisher.send(
        Tasks.INDEX_VERSION, version_id=str(version.id), document_id=str(version.document_id), status=version.status
    )
    if status_changed:
        publisher.send(
            Tasks.VERSION_STATUS_CHANGED,
            document_id=str(version.document_id),
            active_version_id=str(version.id) if version.status == VersionStatus.ACTIVE.value else None,
        )
