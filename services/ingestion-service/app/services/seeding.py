"""Idempotent initial import of the supplied dataset.

Runs in a background thread at startup (and on demand via
``POST /api/imports/run``). For every row of ``doc_metadata.csv`` in upload
order:

* the document family is found or created from the root of the
  ``parent_doc_id`` chain;
* a version with the same family and file hash is **skipped** if its
  paragraphs are present in Elasticsearch, **re-indexed** if the index lost
  them (e.g. the ES volume was reset), and **created** otherwise;
* new versions get a "What's New" alert stamped with the *historical*
  ``upload_timestamp`` and marked as read, so old documents are never
  presented as newly published today.

Progress and errors are persisted in ``import_runs``.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from iris_shared import audit
from iris_shared.config import get_settings
from iris_shared.db import session_scope
from iris_shared.models import DocumentVersion, ImportRun, RegulatoryDocument
from iris_shared.text import sha256_bytes

from ..parsers import ParseError, source_type_for
from . import search_client
from .metadata import MetadataError, import_order, parse_metadata_csv, resolve_family_roots, title_for
from .pipeline import AlertPolicy, VersionInput, index_version, ingest, parse_version

logger = logging.getLogger("ingestion.seed")
_lock = threading.Lock()


def _log(run_id: int, message: str, error: bool = False) -> None:
    logger.log(logging.ERROR if error else logging.INFO, message)
    with session_scope() as s:
        run = s.get(ImportRun, run_id)
        if run is None:
            return
        if error:
            run.errors = [*run.errors, message]
        run.log = [*run.log[-199:], f"{datetime.now(UTC).strftime('%H:%M:%S')} {message}"]


def wait_for_search(timeout_s: float = 180.0) -> bool:
    deadline = time.monotonic() + timeout_s
    delay = 1.0
    while time.monotonic() < deadline:
        if search_client.is_ready():
            return True
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)
    return False


def run_seed() -> int | None:
    """Run the import. Returns the import run id, or None if another import is running."""
    if not _lock.acquire(blocking=False):
        logger.info("import already running; skipped")
        return None
    try:
        return _run_seed_locked()
    finally:
        _lock.release()


def _run_seed_locked() -> int:
    settings = get_settings()
    with session_scope() as s:
        run = ImportRun(status="running", started_at=datetime.now(UTC), log=[], errors=[])
        s.add(run)
        s.flush()
        run_id = run.id

    if not wait_for_search():
        _log(run_id, "Search service / Elasticsearch not ready after 180 s; import aborted", error=True)
        _finish(run_id, "failed")
        return run_id

    try:
        text = settings.metadata_file.read_text(encoding="utf-8")
        rows, errors, convention = parse_metadata_csv(text)
    except (OSError, MetadataError) as exc:
        _log(run_id, f"Cannot read metadata {settings.metadata_file}: {exc}", error=True)
        _finish(run_id, "failed")
        return run_id
    for e in errors:
        _log(run_id, e, error=True)
    _log(run_id, f"Metadata loaded: {len(rows)} document version(s); effective dates {convention}")

    roots, root_errors = resolve_family_roots(rows)
    for e in root_errors:
        _log(run_id, e, error=True)
    by_id = {r.source_id: r for r in rows}

    described = {r.file_name for r in rows}
    if settings.regulations_dir.exists():
        for path in sorted(settings.regulations_dir.iterdir()):
            if path.is_file() and path.name not in described:
                _log(run_id, f"{path.name}: present in /regulations but not described in doc_metadata.csv; skipped", error=True)

    ordered = import_order(rows)
    with session_scope() as s:
        s.get(ImportRun, run_id).files_total = len(ordered)  # type: ignore[union-attr]

    # If the database has no versions yet, clear stale index content from a previous volume.
    with session_scope() as s:
        has_versions = s.scalar(select(DocumentVersion.id).limit(1)) is not None
    if not has_versions:
        try:
            search_client.reset_index()
            _log(run_id, "Fresh database detected: search index reset")
        except search_client.SearchServiceError as exc:
            _log(run_id, f"Index reset failed: {exc}", error=True)

    source_to_version: dict[int, int] = {}
    processed = skipped = failed = 0
    for row in ordered:
        path = settings.regulations_dir / row.file_name
        try:
            outcome, version_id = _import_row(row, roots, by_id, source_to_version, path)
            if version_id is not None:
                source_to_version[row.source_id] = version_id
            if outcome == "skipped":
                skipped += 1
            else:
                processed += 1
            _log(run_id, f"{row.file_name} {row.version_label}: {outcome}")
        except (ParseError, search_client.SearchServiceError, OSError, ValueError) as exc:
            failed += 1
            _log(run_id, f"{row.file_name}: FAILED — {exc}", error=True)
        except Exception as exc:
            failed += 1
            logger.exception("unexpected import failure")
            _log(run_id, f"{row.file_name}: FAILED — unexpected {type(exc).__name__}: {exc}", error=True)
        with session_scope() as s:
            run = s.get(ImportRun, run_id)
            if run:
                run.files_processed, run.files_skipped, run.files_failed = processed, skipped, failed

    reconcile_index(run_id)
    status = "completed" if not (failed or errors or root_errors) else "completed_with_errors"
    _finish(run_id, status)
    with session_scope() as s:
        audit.record(
            s,
            "ingestion",
            "import.finished",
            f"Dataset import {status}: {processed} indexed, {skipped} unchanged, {failed} failed",
            "import_run",
            run_id,
        )
    return run_id


def reconcile_index(run_id: int | None = None) -> None:
    with session_scope() as s:
        valid = list(s.scalars(select(DocumentVersion.id).where(DocumentVersion.status == "indexed")))
    try:
        result = search_client.reconcile(valid)
        if run_id is not None and result.get("deleted"):
            _log(run_id, f"Removed {result['deleted']} orphaned paragraph(s) from the search index")
    except search_client.SearchServiceError as exc:
        if run_id is not None:
            _log(run_id, f"Index reconciliation failed: {exc}", error=True)


def _finish(run_id: int, status: str) -> None:
    with session_scope() as s:
        run = s.get(ImportRun, run_id)
        if run:
            run.status = status
            run.finished_at = datetime.now(UTC)


def _import_row(row, roots, by_id, source_to_version, path: Path) -> tuple[str, int | None]:  # type: ignore[no-untyped-def]
    if not path.exists():
        raise OSError(f"file {path.name} listed in metadata was not found in /regulations")
    source_type = source_type_for(path.name)
    if source_type is None:
        raise ValueError(f"unsupported file type for {path.name}")
    data = path.read_bytes()
    content_hash = sha256_bytes(data)
    root = by_id[roots[row.source_id]]

    with session_scope() as s:
        document = s.scalar(select(RegulatoryDocument).where(RegulatoryDocument.family_key == root.family_key))
        if document is None:
            document = RegulatoryDocument(
                family_key=root.family_key,
                title=title_for(root.file_name),
                regulator=root.regulator,
                jurisdiction=root.jurisdiction,
                category=root.category,
            )
            s.add(document)
            s.flush()

        existing = s.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id, DocumentVersion.content_hash == content_hash)
        )
        if existing is not None and existing.status == "indexed":
            count = search_client.version_paragraph_count(existing.id)
            if count is not None and count == existing.paragraph_count and count > 0:
                return "skipped", existing.id
            index_version(s, document, existing, parse_version(existing))
            return f"re-indexed (index had {count} of {existing.paragraph_count} paragraphs)", existing.id
        if existing is not None:
            # A previous attempt failed: retry indexing on the same version record.
            index_version(s, document, existing, parse_version(existing))
            return "re-processed after earlier failure", existing.id

        clash = s.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id, DocumentVersion.version_label == row.version_label)
        )
        if clash is not None:
            raise ValueError(
                f"version {row.version_label} already exists with different content (hash mismatch); "
                "the dataset file appears to have changed — not overwritten"
            )

        parent_version_id = source_to_version.get(row.parent_source_id) if row.parent_source_id else None
        version = ingest(
            s,
            document,
            VersionInput(
                file_name=row.file_name,
                stored_path=path,
                source_type=source_type,
                content_hash=content_hash,
                file_size=len(data),
                version_label=row.version_label,
                effective_date=row.effective_date,
                uploaded_at=row.uploaded_at,
                origin="seed",
                source_metadata_id=row.source_id,
                parent_version_id=parent_version_id,
                metadata_notes=row.notes,
            ),
            AlertPolicy(source="initial_import", is_read=True, event_time=row.uploaded_at),
        )
        return f"indexed ({version.paragraph_count} clauses)", version.id


def start_background_seed() -> threading.Thread:
    thread = threading.Thread(target=run_seed, name="dataset-import", daemon=True)
    thread.start()
    return thread
