"""Celery tasks owned by ingestion-service (queue: ingestion)."""

from __future__ import annotations

import uuid

from app.api.deps import get_storage
from app.celery_app import celery_app
from app.db import get_sessionmaker
from app.publisher import CeleryPublisher
from app.services.processing import process_version
from iris_common.events import Tasks


@celery_app.task(name=Tasks.PROCESS_VERSION, bind=True, max_retries=3, default_retry_delay=10)
def process_version_task(self, version_id: str) -> str:  # type: ignore[no-untyped-def]
    with get_sessionmaker()() as db:
        process_version(db, uuid.UUID(version_id), get_storage(), CeleryPublisher())
    return version_id
