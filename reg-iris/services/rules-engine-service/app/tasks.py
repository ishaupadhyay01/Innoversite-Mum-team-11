"""Celery tasks owned by rules-engine-service (queue: rules)."""

from __future__ import annotations

import uuid

from celery import chord

from app.celery_app import celery_app
from app.config import get_settings
from app.db import get_sessionmaker
from app.deps import get_schema, get_search_client, get_storage
from app.services import runs
from app.services.traceability import auto_link_rule_set
from iris_common.events import Tasks


@celery_app.task(name=Tasks.EXECUTE_RUN, bind=True)
def execute_run(self, run_id: str) -> str:  # type: ignore[no-untyped-def]
    settings = get_settings()
    rid = uuid.UUID(run_id)
    with get_sessionmaker()() as db:
        run = runs.get_run(db, rid)
        if run.total_trades <= settings.fanout_threshold_rows:
            runs.execute_run_inline(db, rid, get_storage(), get_schema(), settings)
            return run_id
        runs.mark_running(db, rid)
        chunks = run.chunks_total
    # Large dataset: evaluate chunks in parallel across all rules workers, then aggregate.
    chord(evaluate_chunk.s(run_id, i) for i in range(chunks))(finalize_run.s(run_id))
    return run_id


@celery_app.task(name=Tasks.EVALUATE_CHUNK, bind=True, acks_late=True, max_retries=3, default_retry_delay=5)
def evaluate_chunk(self, run_id: str, chunk_index: int) -> int:  # type: ignore[no-untyped-def]
    with get_sessionmaker()() as db:
        try:
            return runs.evaluate_chunk(db, uuid.UUID(run_id), chunk_index, get_storage(), get_schema(), get_settings())
        except Exception as exc:
            raise self.retry(exc=exc) from exc


@celery_app.task(name=Tasks.FINALIZE_RUN)
def finalize_run(_results: list[int], run_id: str) -> str:
    with get_sessionmaker()() as db:
        runs.finalize_run(db, uuid.UUID(run_id))
    return run_id


@celery_app.task(name=Tasks.LINK_RULE_CLAUSES)
def link_rule_clauses(rule_set_id: str) -> int:
    with get_sessionmaker()() as db:
        return auto_link_rule_set(db, uuid.UUID(rule_set_id), get_search_client())
