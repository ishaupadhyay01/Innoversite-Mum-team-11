"""Persisted Impact Matrix runs (analysis_runs + impact_results)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from iris_shared import audit
from iris_shared.db import session_scope
from iris_shared.models import AnalysisRun, ImpactResult
from iris_shared.text import sha256_bytes

from ..registry import Registry
from .core import evaluate_matrix, select_rules, summarize
from .related import related_clauses

logger = logging.getLogger("rules.runs")


def create_run(session: Session, dataset: str, regulators: list[str], rule_ids: list[str]) -> AnalysisRun:
    run = AnalysisRun(
        id=str(uuid.uuid4()),
        kind="impact",
        status="queued",
        dataset=dataset,
        regulators=regulators,
        rule_ids=rule_ids,
        rules_snapshot=[],
        summary={},
        related_clauses={},
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.commit()
    return run


def execute_run(run_id: str, registry: Registry, with_related: bool = True) -> None:
    """Evaluate and persist. Any failure is recorded on the run (never reported as success)."""
    started = time.perf_counter()
    with session_scope() as s:
        run = s.get(AnalysisRun, run_id)
        assert run is not None
        run.status = "running"
        dataset_name, regulators, rule_ids = run.dataset, list(run.regulators), list(run.rule_ids)
    try:
        dataset = registry.load_dataset(dataset_name)
        rules = select_rules(registry.all_rules, regulators, rule_ids)
        if not rules:
            raise ValueError("No rules match the selected regulators / rule ids")
        rows = evaluate_matrix(dataset, rules)
        summary = summarize(rows, dataset, rules)
        summary["dataset_warnings"] = dataset.warnings
        related = {r.id: related_clauses(r) for r in rules} if with_related else {}
        dataset_hash = sha256_bytes(registry.dataset_path(dataset_name).read_bytes())
        with session_scope() as s:
            s.execute(insert(ImpactResult), [{"analysis_id": run_id, "seq": i, **row} for i, row in enumerate(rows)])
            run = s.get(AnalysisRun, run_id)
            assert run is not None
            run.status = "completed"
            run.summary = summary
            run.related_clauses = related
            run.rules_snapshot = [r.to_dict() for r in rules]
            run.dataset_hash = dataset_hash
            run.finished_at = datetime.now(UTC)
            run.duration_ms = round((time.perf_counter() - started) * 1000, 1)
            audit.record(
                s,
                "rules",
                "analysis.completed",
                f"Impact analysis on {dataset_name}: {summary['status_counts']['FAIL']} violations across {summary['unique_impacted_trades']} trades",
                "analysis_run",
                run_id,
                {"rules": len(rules), "trades": dataset.count},
            )
    except Exception as exc:
        logger.exception("analysis run failed")
        with session_scope() as s:
            run = s.get(AnalysisRun, run_id)
            if run:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = datetime.now(UTC)
            audit.record(s, "rules", "analysis.failed", f"Impact analysis failed: {exc}", "analysis_run", run_id)


def run_out(run: AnalysisRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "dataset": run.dataset,
        "dataset_hash": run.dataset_hash,
        "regulators": run.regulators,
        "rule_ids": run.rule_ids,
        "summary": run.summary,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "rules": [
            {k: r.get(k) for k in ("id", "regulator", "description", "rule_source", "applies_when_text", "logic_text", "severity")}
            for r in run.rules_snapshot
        ],
    }


def result_out(r: ImpactResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "trade_id": r.trade_id,
        "asset_class": r.asset_class,
        "regulator": r.regulator,
        "rule_id": r.rule_id,
        "rule_description": r.rule_description,
        "status": r.status,
        "affected_fields": r.affected_fields,
        "actual_values": r.actual_values,
        "expected_condition": r.expected_condition,
        "explanation": r.explanation,
        "rule_source": r.rule_source,
        "severity": r.severity,
        "category": r.category,
        "conditional": r.conditional,
    }


SORTABLE = {
    "seq": ImpactResult.seq,
    "trade_id": ImpactResult.trade_id,
    "asset_class": ImpactResult.asset_class,
    "regulator": ImpactResult.regulator,
    "rule_id": ImpactResult.rule_id,
    "status": ImpactResult.status,
    "category": ImpactResult.category,
}


def filtered_results_stmt(
    run_id: str,
    status: list[str],
    regulator: list[str],
    rule_id: list[str],
    asset_class: list[str],
    trade_id: str | None,
    category: list[str] | None = None,
):  # type: ignore[no-untyped-def]
    stmt = select(ImpactResult).where(ImpactResult.analysis_id == run_id)
    if status:
        stmt = stmt.where(ImpactResult.status.in_(status))
    if regulator:
        stmt = stmt.where(ImpactResult.regulator.in_(regulator))
    if rule_id:
        stmt = stmt.where(ImpactResult.rule_id.in_(rule_id))
    if asset_class:
        stmt = stmt.where(ImpactResult.asset_class.in_(asset_class))
    if category:
        stmt = stmt.where(ImpactResult.category.in_(category))
    if trade_id:
        stmt = stmt.where(ImpactResult.trade_id.ilike(f"%{trade_id.strip()}%"))
    return stmt
