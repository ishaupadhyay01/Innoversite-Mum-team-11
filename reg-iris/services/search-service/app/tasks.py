"""Celery tasks owned by search-service (queue: search). Sent by ingestion-service."""

from __future__ import annotations

import uuid

from app.celery_app import celery_app
from app.db import get_sessionmaker
from app.deps import get_ingestion_client, get_keyword_backend, get_semantic_backend
from app.services.indexer import apply_status_change, index_version
from iris_common.events import Tasks


@celery_app.task(name=Tasks.INDEX_VERSION, bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def index_document_version(self, version_id: str, document_id: str | None = None, status: str | None = None) -> str:  # type: ignore[no-untyped-def]
    with get_sessionmaker()() as db:
        index_version(db, uuid.UUID(version_id), get_ingestion_client(), get_keyword_backend(), get_semantic_backend())
    return version_id


@celery_app.task(
    name=Tasks.VERSION_STATUS_CHANGED, bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5
)
def version_status_changed(self, document_id: str, active_version_id: str | None = None) -> str:  # type: ignore[no-untyped-def]
    with get_sessionmaker()() as db:
        apply_status_change(
            db,
            uuid.UUID(document_id),
            uuid.UUID(active_version_id) if active_version_id else None,
            get_keyword_backend(),
            get_semantic_backend(),
        )
    return document_id
