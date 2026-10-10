"""Rules, Impact Matrix, gap analysis, checklist and trade endpoints."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iris_shared import audit
from iris_shared.db import get_session
from iris_shared.models import AnalysisRun, ImpactResult, RuleSetLoad
from iris_shared.web import ApiError

from ..analysis.core import checklist, combine_and, combined_summary, evaluate_matrix, gap_analysis, select_rules
from ..analysis.export import iter_matrix_csv, summary_csv, verdict_csv
from ..analysis.related import related_clauses
from ..analysis.runs import SORTABLE, create_run, execute_run, filtered_results_stmt, result_out, run_out
from ..analysis.trade_query import SUPPORTED_PATTERNS, parse_trade_query, run_trade_query
from ..engine import STATUSES, build_rule_set
from ..engine.dataset import DatasetError, validate_against_schema
from ..engine.expressions import OPERATORS
from ..registry import Registry

rules_router = APIRouter(prefix="/api/rules", tags=["Rules"])
impact_router = APIRouter(prefix="/api/impact-matrix", tags=["Impact Matrix"])
analysis_router = APIRouter(prefix="/api", tags=["Gap Analysis & Checklist"])
trades_router = APIRouter(prefix="/api/trades", tags=["Trades"])


def get_registry(request: Request) -> Registry:
    return request.app.state.registry


def _dataset(registry: Registry, name: str | None):  # type: ignore[no-untyped-def]
    name = name or registry.default_dataset
    if not name:
        raise ApiError(404, "no_dataset", "No trade dataset is available in the trades directory")
    try:
        return registry.load_dataset(name)
    except DatasetError as exc:
        raise ApiError(404, "dataset_error", str(exc)) from exc


# ----------------------------------------------------------------------------- rules


@rules_router.get("", summary="List rule sets and rules (source JSON, normalised logic, notes)")
def list_rules(registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    return {
        "loaded_at": registry.loaded_at.isoformat() if registry.loaded_at else None,
        "rules_dir": str(registry.rules_dir),
        "rule_sets": [rs.to_dict() for rs in registry.rule_sets],
        "total_rules": len(registry.all_rules),
        "valid_rules": sum(1 for r in registry.all_rules if r.valid),
        "regulators": registry.regulators,
        "schema": {
            "source": registry.schema.source if registry.schema else None,
            "fields": sorted(registry.schema.field_names) if registry.schema else [],
            "required": registry.schema.required if registry.schema else [],
            "normalization_notes": registry.schema.notes if registry.schema else [],
        },
        "overlay": {
            "source": registry.overlay.source,
            "field_aliases": registry.overlay.field_aliases,
            "rules": list(registry.overlay.rules),
        },
        "load_errors": registry.load_errors,
    }


@rules_router.get("/operators", summary="Supported rule expression operators")
def operators() -> list[dict[str, Any]]:
    return [{"operator": s.name, "min_args": s.min_args, "max_args": s.max_args, "description": s.description} for s in OPERATORS.values()]


@rules_router.post("/validate", summary="Validate a rule-set JSON document without saving it")
def validate_rules(
    rule_set: dict[str, Any] = Body(
        ...,
        examples=[
            {
                "regulator": "Demo",
                "rules": [{"id": "DEMO-1", "description": "Price must be positive", "logic": {">": [{"var": "Price"}, 0]}}],
            }
        ],
    ),
    registry: Registry = Depends(get_registry),
) -> dict[str, Any]:
    raw = json.dumps(rule_set, sort_keys=True).encode()
    known = registry.schema.field_names if registry.schema else set()
    rs = build_rule_set(rule_set, "<request>", raw, known, registry.overlay)
    existing = {r.id for r in registry.all_rules}
    for rule in rs.rules:
        if rule.id in existing:
            rule.warnings.append(f"rule id {rule.id!r} already exists in the loaded rule sets")
    return {"valid": rs.valid, **rs.to_dict()}


@rules_router.post("/reload", summary="Reload rule files from disk (zero-code rule updates)")
def reload_rules(registry: Registry = Depends(get_registry), session: Session = Depends(get_session)) -> dict[str, Any]:
    before = {r.id for r in registry.all_rules}
    registry.reload()
    after = {r.id for r in registry.all_rules}
    for rs in registry.rule_sets:
        session.add(
            RuleSetLoad(
                file_name=rs.file_name,
                regulator=rs.regulator,
                content_hash=rs.content_hash,
                rule_count=len(rs.rules),
                valid=rs.valid,
                errors=rs.errors + [f"{r.id}: {e}" for r in rs.rules for e in r.errors],
            )
        )
    audit.record(
        session,
        "rules",
        "rules.reloaded",
        f"Rules reloaded: {len(after)} rule(s) from {len(registry.rule_sets)} file(s)",
        detail={"added": sorted(after - before), "removed": sorted(before - after)},
    )
    session.commit()
    return {
        "rule_sets": len(registry.rule_sets),
        "rules": len(after),
        "added": sorted(after - before),
        "removed": sorted(before - after),
        "invalid": [r.id for r in registry.all_rules if not r.valid],
        "load_errors": registry.load_errors,
    }


@rules_router.get("/{rule_id}", summary="Rule definition with related regulatory text (keyword match)")
def get_rule(rule_id: str, registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    rule = registry.rule(rule_id)
    if rule is None:
        raise ApiError(404, "rule_not_found", f"Rule {rule_id} not found")
    return {**rule.to_dict(), "related_text": related_clauses(rule, limit=3)}


# ----------------------------------------------------------------------------- impact matrix


class ImpactRequest(BaseModel):
    dataset: str | None = Field(None, description="Trade CSV in the trades folder (default sample_trades.csv)")
    regulators: list[str] = Field(default_factory=list, description="Empty = all rule sets")
    rule_ids: list[str] = Field(
        default_factory=list,
        description="Empty = all rules of the selected regulators. The selected rules are combined with AND per trade (summary.combined, /{id}/trades).",
    )
    run_async: bool = Field(False, description="Return 202 immediately and poll GET /api/impact-matrix/{id}")
    include_related_text: bool = True


@impact_router.post("", status_code=status.HTTP_201_CREATED, summary="Run impact analysis (trades × JSON rules)")
def run_impact(
    body: ImpactRequest,
    background: BackgroundTasks,
    registry: Registry = Depends(get_registry),
    session: Session = Depends(get_session),
) -> Response:
    dataset = body.dataset or registry.default_dataset
    if not dataset:
        raise ApiError(404, "no_dataset", "No trade dataset available")
    try:
        registry.dataset_path(dataset)
    except DatasetError as exc:
        raise ApiError(404, "dataset_error", str(exc)) from exc
    if not select_rules(registry.all_rules, body.regulators, body.rule_ids):
        raise ApiError(422, "no_rules", "No rules match the selected regulators / rule ids")
    run = create_run(session, dataset, body.regulators, body.rule_ids)
    if body.run_async:
        background.add_task(execute_run, run.id, registry, body.include_related_text)
        return Response(
            content=json.dumps({"id": run.id, "status": "queued", "status_url": f"/api/impact-matrix/{run.id}"}),
            status_code=202,
            media_type="application/json",
        )
    execute_run(run.id, registry, body.include_related_text)
    session.expire_all()
    run = session.get(AnalysisRun, run.id)
    assert run is not None
    if run.status == "failed":
        raise ApiError(500, "analysis_failed", run.error or "analysis failed", {"analysis_id": run.id})
    return Response(content=json.dumps(run_out(run), default=str), status_code=201, media_type="application/json")


@impact_router.get("", summary="List analysis runs (newest first)")
def list_runs(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    runs = session.scalars(select(AnalysisRun).order_by(AnalysisRun.started_at.desc()).limit(limit)).all()
    out = []
    for r in runs:
        d = run_out(r)
        d.pop("rules", None)
        out.append(d)
    return out


@impact_router.get("/latest", summary="Most recent completed analysis summary")
def latest_run(session: Session = Depends(get_session)) -> dict[str, Any] | None:
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.status == "completed").order_by(AnalysisRun.finished_at.desc()).limit(1))
    return run_out(run) if run else None


def _get_run(session: Session, analysis_id: str) -> AnalysisRun:
    run = session.get(AnalysisRun, analysis_id)
    if run is None:
        raise ApiError(404, "analysis_not_found", f"Analysis {analysis_id} not found")
    return run


@impact_router.get("/{analysis_id}", summary="Impact Matrix rows (server-side filter, sort, pagination)")
def get_matrix(
    analysis_id: str,
    status_: list[str] = Query(default=[], alias="status", description="PASS | FAIL | NOT_APPLICABLE | ERROR"),
    regulator: list[str] = Query(default=[]),
    rule_id: list[str] = Query(default=[]),
    asset_class: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    trade_id: str | None = Query(None, max_length=64, description="Substring match on Trade_ID"),
    sort_by: Literal["seq", "trade_id", "asset_class", "regulator", "rule_id", "status", "category"] = "seq",
    sort_dir: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run(session, analysis_id)
    bad = [s for s in status_ if s not in STATUSES]
    if bad:
        raise ApiError(422, "invalid_status", f"Unknown status value(s): {', '.join(bad)}")
    stmt = filtered_results_stmt(analysis_id, status_, regulator, rule_id, asset_class, trade_id, category)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE[sort_by]
    order = column.asc() if sort_dir == "asc" else column.desc()
    rows = session.scalars(stmt.order_by(order, ImpactResult.seq).offset((page - 1) * page_size).limit(page_size)).all()
    filtered_trades = session.scalar(select(func.count(func.distinct(stmt.subquery().c.trade_id)))) or 0
    return {
        "analysis": run_out(run),
        "items": [result_out(r) for r in rows],
        "total": total,
        "distinct_trades": filtered_trades,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def _trade_verdicts(session: Session, run: AnalysisRun) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The run's selected rules combined with AND, one verdict per trade (computed from the stored rows)."""
    if run.status != "completed":
        raise ApiError(409, "analysis_not_completed", f"Analysis is {run.status}")
    rule_ids = [r["id"] for r in run.rules_snapshot]
    stored = session.scalars(select(ImpactResult).where(ImpactResult.analysis_id == run.id).order_by(ImpactResult.seq)).all()
    verdicts = combine_and([result_out(r) for r in stored], rule_ids)
    return verdicts, combined_summary(verdicts, rule_ids)


@impact_router.get("/{analysis_id}/trades", summary="One verdict per trade: the selected rules combined with AND")
def get_trade_verdicts(
    analysis_id: str,
    overall: list[str] = Query(default=[], description="PASS | FAIL | NOT_APPLICABLE | ERROR"),
    trade_id: str | None = Query(None, max_length=64, description="Substring match on Trade_ID"),
    asset_class: list[str] = Query(default=[]),
    failed_rule: list[str] = Query(default=[], description="Only trades that fail this rule (any of the given ids)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run(session, analysis_id)
    bad = [s for s in overall if s not in STATUSES]
    if bad:
        raise ApiError(422, "invalid_status", f"Unknown status value(s): {', '.join(bad)}")
    verdicts, combined = _trade_verdicts(session, run)
    items = _filter_verdicts(verdicts, overall, trade_id, asset_class, failed_rule)
    total = len(items)
    return {
        "analysis_id": run.id,
        "combined": combined,
        "items": items[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def _filter_verdicts(
    verdicts: list[dict[str, Any]], overall: list[str], trade_id: str | None, asset_class: list[str], failed_rule: list[str]
) -> list[dict[str, Any]]:
    needle = (trade_id or "").strip().lower()
    wanted_rules = {r.upper() for r in failed_rule}
    return [
        v
        for v in verdicts
        if (not overall or v["overall"] in overall)
        and (not needle or needle in v["trade_id"].lower())
        and (not asset_class or v["asset_class"] in asset_class)
        and (not wanted_rules or wanted_rules & {r.upper() for r in v["failed_rule_ids"]})
    ]


@impact_router.get("/{analysis_id}/export/trades", summary="Download the per-trade AND verdicts as CSV")
def export_trade_verdicts(
    analysis_id: str,
    overall: list[str] = Query(default=[]),
    trade_id: str | None = Query(None, max_length=64),
    asset_class: list[str] = Query(default=[]),
    failed_rule: list[str] = Query(default=[]),
    session: Session = Depends(get_session),
) -> Response:
    run = _get_run(session, analysis_id)
    verdicts, combined = _trade_verdicts(session, run)
    items = _filter_verdicts(verdicts, overall, trade_id, asset_class, failed_rule)
    suffix = "_".join(overall).lower() or "all"
    return Response(
        content=verdict_csv(items, combined["expression"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trade_verdicts_{suffix}_{analysis_id[:8]}.csv"'},
    )


@impact_router.get("/{analysis_id}/results/{result_id}", summary="One Impact Matrix row with trade, rule and related text")
def get_result(
    analysis_id: str, result_id: int, registry: Registry = Depends(get_registry), session: Session = Depends(get_session)
) -> dict[str, Any]:
    run = _get_run(session, analysis_id)
    row = session.get(ImpactResult, result_id)
    if row is None or row.analysis_id != analysis_id:
        raise ApiError(404, "result_not_found", f"Result {result_id} not found in analysis {analysis_id}")
    rule = next((r for r in run.rules_snapshot if r["id"] == row.rule_id), None)
    trade = None
    try:
        dataset = registry.load_dataset(run.dataset)
        trade = dataset.by_id().get(row.trade_id)
    except DatasetError:
        trade = None
    return {
        "result": result_out(row),
        "trade": trade,
        "rule": rule,
        "related_text": (run.related_clauses or {}).get(row.rule_id, {"status": "not_computed", "items": []}),
        "analysis": {"id": run.id, "dataset": run.dataset, "dataset_hash": run.dataset_hash, "finished_at": run.finished_at},
    }


@impact_router.get("/{analysis_id}/export", summary="Download the Impact Matrix as CSV (formula-injection safe)")
def export_matrix(
    analysis_id: str,
    status_: list[str] = Query(default=[], alias="status"),
    regulator: list[str] = Query(default=[]),
    rule_id: list[str] = Query(default=[]),
    asset_class: list[str] = Query(default=[]),
    trade_id: str | None = Query(None, max_length=64),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    run = _get_run(session, analysis_id)
    if run.status != "completed":
        raise ApiError(409, "analysis_not_completed", f"Analysis is {run.status}")
    stmt = filtered_results_stmt(analysis_id, status_, regulator, rule_id, asset_class, trade_id).order_by(ImpactResult.seq)
    rows = [result_out(r) for r in session.scalars(stmt).all()]
    suffix = "_".join(status_).lower() or "all"
    filename = f"impact_matrix_{run.dataset.rsplit('.', 1)[0]}_{suffix}_{analysis_id[:8]}.csv"
    return StreamingResponse(
        iter_matrix_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@impact_router.get("/{analysis_id}/export/summary", summary="Download the analysis summary as CSV")
def export_summary(analysis_id: str, session: Session = Depends(get_session)) -> Response:
    run = _get_run(session, analysis_id)
    if run.status != "completed":
        raise ApiError(409, "analysis_not_completed", f"Analysis is {run.status}")
    return Response(
        content=summary_csv(run.summary),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="impact_summary_{analysis_id[:8]}.csv"'},
    )


# ----------------------------------------------------------------------------- gap analysis & checklist


class GapRequest(BaseModel):
    dataset: str | None = None
    regulators: list[str] = Field(default_factory=list)
    include_schema_validation: bool = True


@analysis_router.post("/gap-analysis", summary="Gap analysis: rule findings by category, plus optional schema validation")
def run_gap_analysis(body: GapRequest, registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    dataset = _dataset(registry, body.dataset)
    rules = select_rules(registry.all_rules, body.regulators)
    if not rules:
        raise ApiError(422, "no_rules", "No rules match the selected regulators")
    rows = evaluate_matrix(dataset, rules)
    schema_findings = validate_against_schema(dataset, registry.schema) if body.include_schema_validation and registry.schema else None
    result = gap_analysis(rows, schema_findings)
    return {
        "dataset": dataset.name,
        "trades": dataset.count,
        "regulators": sorted({r.regulator for r in rules}),
        "rules_evaluated": [r.id for r in rules],
        "dataset_warnings": dataset.warnings,
        **result,
        "notes": [
            "rule_findings come from the JSON rule files; schema_findings come from the reporting JSON Schema "
            "and are reported separately — they are independent checks and are not added together."
        ],
    }


@analysis_router.get("/checklist", summary="Compliance checklist per rule (dataset-wide or for one trade)")
def get_checklist(
    dataset: str | None = None,
    regulator: list[str] = Query(default=[]),
    trade_id: str | None = Query(None, max_length=64),
    registry: Registry = Depends(get_registry),
) -> dict[str, Any]:
    ds = _dataset(registry, dataset)
    rules = select_rules(registry.all_rules, regulator)
    if not rules:
        raise ApiError(422, "no_rules", "No rules match the selected regulators")
    if trade_id is not None and trade_id not in ds.by_id():
        raise ApiError(404, "trade_not_found", f"Trade {trade_id} not found in {ds.name}")
    rows = evaluate_matrix(ds, rules)
    result = checklist(rows, rules, trade_id)
    result.update({"dataset": ds.name, "trades": ds.count, "regulators": sorted({r.regulator for r in rules})})
    if trade_id:
        result["trade"] = ds.by_id()[trade_id]
    return result


# ----------------------------------------------------------------------------- trades


@trades_router.get("/datasets", summary="Available synthetic trade datasets")
def datasets(registry: Registry = Depends(get_registry)) -> list[dict[str, Any]]:
    out = []
    for path in registry.datasets():
        try:
            ds = registry.load_dataset(path.name)
            out.append(
                {
                    "name": path.name,
                    "trades": ds.count,
                    "columns": ds.columns,
                    "warnings": ds.warnings,
                    "default": path.name == registry.default_dataset,
                }
            )
        except DatasetError as exc:
            out.append({"name": path.name, "trades": 0, "columns": [], "warnings": [str(exc)], "default": False})
    return out


class TradeQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=300)
    dataset: str | None = None
    limit: int = Field(50, ge=1, le=500)


@trades_router.post("/query", summary="Answer a supported trade-data question with structured filters (no keyword search)")
def trade_query(body: TradeQueryRequest, registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    if registry.schema is None:
        raise ApiError(503, "schema_unavailable", "Reporting schema not loaded")
    ds = _dataset(registry, body.dataset)
    parsed = parse_trade_query(body.question, registry.schema)
    if not parsed.matched:
        return {"matched": False, "message": parsed.message, "supported_patterns": SUPPORTED_PATTERNS}
    matches = run_trade_query(parsed, ds)
    return {
        "matched": True,
        "dataset": ds.name,
        "interpretation": " AND ".join(c.describe() for c in parsed.conditions),
        "conditions": [{"field": c.field, "op": c.op, "value": c.value} for c in parsed.conditions],
        "count": len(matches),
        "count_only": parsed.count_only,
        "trades": [] if parsed.count_only else matches[: body.limit],
        "method": "deterministic pattern parser over the trade CSV (see SUPPORTED_PATTERNS)",
    }


@trades_router.get("", summary="List trades with optional filters")
def list_trades(
    dataset: str | None = None,
    asset_class: list[str] = Query(default=[]),
    q: str | None = Query(None, max_length=64, description="Substring match on Trade_ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    registry: Registry = Depends(get_registry),
) -> dict[str, Any]:
    ds = _dataset(registry, dataset)
    trades = ds.trades
    if asset_class:
        trades = [t for t in trades if t.get("Asset_Class") in asset_class]
    if q:
        trades = [t for t in trades if q.lower() in str(t.get("Trade_ID", "")).lower()]
    return {
        "dataset": ds.name,
        "total": len(trades),
        "page": page,
        "page_size": page_size,
        "items": trades[(page - 1) * page_size : page * page_size],
    }


@trades_router.get("/{trade_id}", summary="One trade with its per-rule checklist")
def get_trade(trade_id: str, dataset: str | None = None, registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    ds = _dataset(registry, dataset)
    trade = ds.by_id().get(trade_id)
    if trade is None:
        raise ApiError(404, "trade_not_found", f"Trade {trade_id} not found in {ds.name}")
    rules = registry.all_rules
    single = type(ds)(name=ds.name, columns=ds.columns, trades=[trade], raw_rows=[], warnings=[])
    rows = evaluate_matrix(single, rules)
    return {"dataset": ds.name, "trade": trade, "checklist": checklist(rows, rules, trade_id)["items"]}
