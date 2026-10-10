"""Asynchronous processing of user uploads (job status: queued -> processing -> indexed | failed)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from iris_shared import audit
from iris_shared.db import session_scope
from iris_shared.models import RegulatoryDocument, UploadJob

from ..parsers import ParseError
from . import search_client
from .metadata import family_key_for, title_for
from .pipeline import AlertPolicy, VersionInput, ingest, latest_version, next_version_seq
from .seeding import reconcile_index

logger = logging.getLogger("ingestion.uploads")


def _set_job(job_id: str, status: str, detail: str | None = None, **fields: object) -> None:
    with session_scope() as s:
        job = s.get(UploadJob, job_id)
        if job is None:
            return
        job.status = status
        job.detail = detail
        for k, v in fields.items():
            setattr(job, k, v)


def _unique_family_key(session, base: str) -> str:  # type: ignore[no-untyped-def]
    key, n = base, 2
    while session.scalar(select(RegulatoryDocument.id).where(RegulatoryDocument.family_key == key)) is not None:
        key = f"{base}_{n}"
        n += 1
    return key


def process_upload(job_id: str) -> None:
    _set_job(job_id, "processing")
    try:
        with session_scope() as s:
            job = s.get(UploadJob, job_id)
            assert job is not None
            req = dict(job.request)
            now = datetime.now(UTC)
            if req.get("document_id"):
                document = s.get(RegulatoryDocument, int(req["document_id"]))
                if document is None:
                    raise ValueError(f"document {req['document_id']} no longer exists")
                parent = latest_version(s, document.id)
            else:
                document = RegulatoryDocument(
                    family_key=_unique_family_key(s, family_key_for(req["file_name"])),
                    title=(req.get("title") or title_for(req["file_name"]))[:300],
                    regulator=req["regulator"],
                    jurisdiction=req.get("jurisdiction"),
                    category=req.get("category"),
                )
                s.add(document)
                s.flush()
                parent = None
            label = req.get("version_label") or f"v{next_version_seq(s, document.id)}.0"
            effective = date.fromisoformat(req["effective_date"]) if req.get("effective_date") else None
            version = ingest(
                s,
                document,
                VersionInput(
                    file_name=req["file_name"],
                    stored_path=Path(req["stored_path"]),
                    source_type=req["source_type"],
                    content_hash=req["content_hash"],
                    file_size=int(req["file_size"]),
                    version_label=label,
                    effective_date=effective or (parent.effective_date if parent else None),
                    uploaded_at=now,
                    origin="upload",
                    parent_version_id=parent.id if parent else None,
                ),
                AlertPolicy(source="upload", is_read=False, event_time=now),
            )
            s.flush()
            job.status = "indexed"
            job.detail = f"Indexed {version.paragraph_count} clause(s)"
            job.document_id = document.id
            job.version_id = version.id
            audit.record(
                s,
                "ingestion",
                "document.uploaded",
                f"Uploaded {version.file_name} as {version.version_label}",
                "document_version",
                version.id,
            )
    except ParseError as exc:
        _fail(job_id, f"Extraction failed: {exc}")
    except search_client.SearchServiceError as exc:
        _fail(job_id, f"Indexing failed: {exc}")
        reconcile_index()
    except Exception as exc:
        logger.exception("upload processing failed")
        _fail(job_id, f"{type(exc).__name__}: {exc}")
        reconcile_index()


def _fail(job_id: str, message: str) -> None:
    _set_job(job_id, "failed", message)
    with session_scope() as s:
        audit.record(s, "ingestion", "document.upload_failed", message, "upload_job", job_id)
