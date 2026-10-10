"""Asynchronous contracts between services.

Services never import each other's code. They communicate:
* synchronously over REST (see docs/SERVICE_COMMUNICATION.md), and
* asynchronously by sending **Celery tasks by name** onto the target service's queue.

The task names, queues and payload schemas below are the contract; the owning team
implements the task, any team may send it.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class Queues:
    INGESTION = "ingestion"
    SEARCH = "search"
    RULES = "rules"


class Tasks:
    # owned by ingestion-service
    PROCESS_VERSION = "ingestion.process_version"
    # owned by search-service
    INDEX_VERSION = "search.index_document_version"
    VERSION_STATUS_CHANGED = "search.version_status_changed"
    # owned by rules-engine-service
    EXECUTE_RUN = "rules.execute_run"
    EVALUATE_CHUNK = "rules.evaluate_chunk"
    FINALIZE_RUN = "rules.finalize_run"
    LINK_RULE_CLAUSES = "rules.link_rule_clauses"


TASK_ROUTES = {
    "ingestion.*": {"queue": Queues.INGESTION},
    "search.*": {"queue": Queues.SEARCH},
    "rules.*": {"queue": Queues.RULES},
}


class IndexVersionEvent(BaseModel):
    """Sent by ingestion when a version has been parsed into clauses."""

    version_id: UUID
    document_id: UUID
    status: str  # ACTIVE | INACTIVE


class VersionStatusChangedEvent(BaseModel):
    """Sent by ingestion when the ACTIVE version of a document changes."""

    document_id: UUID
    active_version_id: UUID | None
    effective_date: date | None = None
