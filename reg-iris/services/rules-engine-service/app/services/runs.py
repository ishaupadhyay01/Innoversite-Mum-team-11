"""Run execution: chunked evaluation of trades × rules with bulk result inserts.

Small datasets run inside one Celery task, chunk by chunk. Above ``fanout_threshold_rows`` the run is
split into a Celery chord: N parallel ``rules.evaluate_chunk`` tasks + ``rules.finalize_run``. Each chunk
is idempotent (its rows are deleted before insert) so retries are safe.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.engine import RuleSpec, evaluate_trade
from app.models import RunStatus, ValidationResult, ValidationRun
from app.services.datasets import get_dataset
from app.services.rulesets import resolve_rule_sets, to_specs
from app.storage import FileStorage
from app.trades.reader import iter_trade_chunks
from app.trades.schema import ReportingSchema
from iris_common.errors import ConflictError, NotFoundError

log = logging.getLogger(__name__)


def create_run(
    db: Session,
    settings: Settings,
    dataset_id: uuid.UUID,
    rule_set_ids: list[uuid.UUID],
    document_version_id: uuid.UUID | None,
    actor: str | None,
) -> ValidationRun:
    ds = get_dataset(db, dataset_id)
    if ds.status == "INVALID":
        raise ConflictError(
            "Dataset failed validation and cannot be analysed",
            code="DATASET_INVALID",
            details={"errors": ds.validation.get("errors", [])},
        )
    rule_sets = resolve_rule_sets(db, rule_set_ids)
    specs = to_specs(rule_sets)
    run = ValidationRun(
        dataset_id=ds.id,
        rule_set_ids=[str(rs.id) for rs in rule_sets],
        document_version_id=document_version_id,
        status=RunStatus.QUEUED.value,
        total_trades=ds.row_count,
        total_rules=len(specs),
        chunks_total=max(1, math.ceil(ds.row_count / settings.chunk_size)),
        rule_snapshot=[{**s.__dict__, "fields": list(s.fields)} for s in specs],
        requested_by=actor,
    )
    db.add(run)
    db.flush()
    return run


def get_run(db: Session, run_id: uuid.UUID) -> ValidationRun:
    run = db.get(ValidationRun, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found")
    return run


def _specs(run: ValidationRun) -> list[RuleSpec]:
    return [RuleSpec(**{**s, "fields": tuple(s["fields"])}) for s in run.rule_snapshot]


def evaluate_chunk(
    db: Session, run_id: uuid.UUID, chunk_index: int, storage: FileStorage, schema: ReportingSchema, settings: Settings
) -> int:
    run = get_run(db, run_id)
    ds = get_dataset(db, run.dataset_id)
    specs = _specs(run)
    start = chunk_index * settings.chunk_size
    db.execute(
        delete(ValidationResult).where(
            ValidationResult.run_id == run_id,
            ValidationResult.row_number > start,
            ValidationResult.row_number <= start + settings.chunk_size,
        )
    )
    rows: list[dict[str, Any]] = []
    count = 0
    for batch in iter_trade_chunks(
        storage.path(ds.storage_key), schema, settings.chunk_size, skip_rows=start, max_rows=settings.chunk_size
    ):
        for row_number, trade in batch:
            count += 1
            for spec, outcome in zip(specs, evaluate_trade(trade, specs), strict=True):
                rows.append(
                    {
                        "run_id": run_id,
                        "row_number": row_number,
                        "trade_id": trade.get("Trade_ID"),
                        "asset_class": trade.get("Asset_Class"),
                        "rule_id": uuid.UUID(spec.rule_id) if spec.rule_id else None,
                        "rule_code": spec.code,
                        "regulator": spec.regulator,
                        "severity": spec.severity,
                        "status": outcome.status.value,
                        "explanation": outcome.explanation,
                        "field_values": outcome.field_values,
                        "clause_ref": spec.clause_ref,
                        "citation_label": spec.citation,
                        "source_version_id": run.document_version_id,
                    }
                )
                if len(rows) >= settings.insert_batch_size:
                    db.execute(insert(ValidationResult), rows)
                    rows.clear()
    if rows:
        db.execute(insert(ValidationResult), rows)
    db.execute(
        update(ValidationRun).where(ValidationRun.id == run_id).values(chunks_done=ValidationRun.chunks_done + 1)
    )
    db.commit()
    return count


def mark_running(db: Session, run_id: uuid.UUID) -> ValidationRun:
    run = get_run(db, run_id)
    run.status = RunStatus.RUNNING.value
    run.started_at = datetime.now(UTC)
    run.chunks_done = 0
    db.commit()
    return run


def finalize_run(db: Session, run_id: uuid.UUID) -> ValidationRun:
    run = get_run(db, run_id)
    counts = dict(
        db.execute(
            select(ValidationResult.status, func.count())
            .where(ValidationResult.run_id == run_id)
            .group_by(ValidationResult.status)
        ).all()
    )
    failing_trades = (
        db.scalar(
            select(func.count(func.distinct(ValidationResult.row_number))).where(
                ValidationResult.run_id == run_id, ValidationResult.status == "FAIL"
            )
        )
        or 0
    )
    run.summary = {
        "passed": counts.get("PASS", 0),
        "failed": counts.get("FAIL", 0),
        "not_applicable": counts.get("NOT_APPLICABLE", 0),
        "errors": counts.get("ERROR", 0),
        "trades_with_failures": failing_trades,
        "compliant_trades": max(0, run.total_trades - failing_trades),
    }
    run.status = RunStatus.COMPLETED.value
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def fail_run(db: Session, run_id: uuid.UUID, error: str) -> None:
    db.rollback()
    run = get_run(db, run_id)
    run.status = RunStatus.FAILED.value
    run.error_message = error[:2000]
    run.finished_at = datetime.now(UTC)
    db.commit()


def execute_run_inline(
    db: Session, run_id: uuid.UUID, storage: FileStorage, schema: ReportingSchema, settings: Settings
) -> ValidationRun:
    run = mark_running(db, run_id)
    try:
        for chunk in range(run.chunks_total):
            evaluate_chunk(db, run_id, chunk, storage, schema, settings)
        return finalize_run(db, run_id)
    except Exception as exc:
        log.exception("run_failed", extra={"run_id": str(run_id)})
        fail_run(db, run_id, f"{exc.__class__.__name__}: {exc}")
        return get_run(db, run_id)


def status_counts_expr():  # type: ignore[no-untyped-def]
    return (
        func.sum(case((ValidationResult.status == "PASS", 1), else_=0)).label("passed"),
        func.sum(case((ValidationResult.status == "FAIL", 1), else_=0)).label("failed"),
        func.sum(case((ValidationResult.status == "NOT_APPLICABLE", 1), else_=0)).label("na"),
        func.sum(case((ValidationResult.status == "ERROR", 1), else_=0)).label("errors"),
    )
