"""Impact Matrix queries: flat results, trade × rule pivot, statistics and CSV export."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models import ValidationResult, ValidationRun
from app.schemas import MatrixColumn, MatrixPage, MatrixRow, RuleStats, RunStats
from app.services.runs import get_run, status_counts_expr

SORTABLE = {
    "row_number": ValidationResult.row_number,
    "trade_id": ValidationResult.trade_id,
    "rule_code": ValidationResult.rule_code,
    "status": ValidationResult.status,
    "severity": ValidationResult.severity,
    "regulator": ValidationResult.regulator,
}


def filtered(
    run_id: uuid.UUID,
    *,
    status: list[str] | None = None,
    rule_code: list[str] | None = None,
    regulator: list[str] | None = None,
    severity: list[str] | None = None,
    asset_class: list[str] | None = None,
    trade_id: str | None = None,
    q: str | None = None,
) -> Select:  # type: ignore[type-arg]
    stmt = select(ValidationResult).where(ValidationResult.run_id == run_id)
    if status:
        stmt = stmt.where(ValidationResult.status.in_(status))
    if rule_code:
        stmt = stmt.where(ValidationResult.rule_code.in_(rule_code))
    if regulator:
        stmt = stmt.where(ValidationResult.regulator.in_(regulator))
    if severity:
        stmt = stmt.where(ValidationResult.severity.in_(severity))
    if asset_class:
        stmt = stmt.where(ValidationResult.asset_class.in_(asset_class))
    if trade_id:
        stmt = stmt.where(ValidationResult.trade_id.ilike(f"%{trade_id}%"))
    if q:
        stmt = stmt.where(ValidationResult.explanation.ilike(f"%{q}%"))
    return stmt


def page_results(db: Session, stmt: Select, sort: str, desc: bool, offset: int, size: int):  # type: ignore[no-untyped-def,type-arg]
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTABLE.get(sort, ValidationResult.row_number)
    rows = db.scalars(
        stmt.order_by(col.desc() if desc else col.asc(), ValidationResult.id).offset(offset).limit(size)
    ).all()
    return rows, total


def pivot(db: Session, run: ValidationRun, *, only_failing: bool, offset: int, size: int, page: int) -> MatrixPage:
    columns = [
        MatrixColumn(
            rule_code=s["code"],
            regulator=s["regulator"],
            description=s["description"],
            severity=s["severity"],
            citation_label=s.get("citation") or s.get("clause_ref"),
        )
        for s in run.rule_snapshot
    ]
    trades = (
        select(ValidationResult.row_number)
        .where(ValidationResult.run_id == run.id)
        .group_by(ValidationResult.row_number)
    )
    if only_failing:
        trades = trades.having(func.sum(case((ValidationResult.status == "FAIL", 1), else_=0)) > 0)
    total = db.scalar(select(func.count()).select_from(trades.subquery())) or 0
    row_numbers = list(db.scalars(trades.order_by(ValidationResult.row_number).offset(offset).limit(size)))
    cells: dict[int, MatrixRow] = {}
    if row_numbers:
        for r in db.scalars(
            select(ValidationResult).where(
                ValidationResult.run_id == run.id, ValidationResult.row_number.in_(row_numbers)
            )
        ):
            row = cells.setdefault(
                r.row_number,
                MatrixRow(
                    trade_id=r.trade_id, row_number=r.row_number, asset_class=r.asset_class, fail_count=0, cells={}
                ),
            )
            row.cells[r.rule_code] = r.status  # type: ignore[assignment]
            row.fail_count += r.status == "FAIL"
    return MatrixPage(
        columns=columns, rows=[cells[n] for n in row_numbers if n in cells], total=total, page=page, size=size
    )


def stats(db: Session, run_id: uuid.UUID) -> RunStats:
    run = get_run(db, run_id)
    base = ValidationResult.run_id == run_id
    by_rule = []
    for code, reg, sev, p, f, na, e in db.execute(
        select(ValidationResult.rule_code, ValidationResult.regulator, ValidationResult.severity, *status_counts_expr())
        .where(base)
        .group_by(ValidationResult.rule_code, ValidationResult.regulator, ValidationResult.severity)
        .order_by(ValidationResult.rule_code)
    ):
        by_rule.append(
            RuleStats(
                rule_code=code,
                regulator=reg,
                severity=sev,
                passed=p or 0,
                failed=f or 0,
                not_applicable=na or 0,
                errors=e or 0,
                fail_rate=round((f or 0) / ((p or 0) + (f or 0)), 4) if (p or f) else 0.0,
            )
        )

    def grouped(col) -> dict[str, dict[str, int]]:  # type: ignore[no-untyped-def]
        out = {}
        for key, p, f, na, e in db.execute(select(col, *status_counts_expr()).where(base).group_by(col)):
            out[key or "UNKNOWN"] = {"passed": p or 0, "failed": f or 0, "not_applicable": na or 0, "errors": e or 0}
        return out

    s = run.summary or {}
    passed, failed = s.get("passed", 0), s.get("failed", 0)
    return RunStats(
        run_id=run.id,
        status=run.status,
        total_trades=run.total_trades,
        total_checks=passed + failed + s.get("not_applicable", 0) + s.get("errors", 0),
        passed=passed,
        failed=failed,
        not_applicable=s.get("not_applicable", 0),
        errors=s.get("errors", 0),
        pass_rate=round(passed / (passed + failed), 4) if passed + failed else 1.0,
        trades_with_failures=s.get("trades_with_failures", 0),
        compliant_trades=s.get("compliant_trades", 0),
        by_rule=by_rule,
        by_regulator=grouped(ValidationResult.regulator),
        by_asset_class=grouped(ValidationResult.asset_class),
    )


EXPORT_COLUMNS = [
    "Trade_ID",
    "Row",
    "Asset_Class",
    "Regulator",
    "Rule_ID",
    "Severity",
    "Status",
    "Explanation",
    "Clause",
    "Citation",
    "Field_Values",
]


def export_csv(db: Session, stmt: Select, batch: int = 5000) -> Iterator[str]:  # type: ignore[type-arg]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    yield buf.getvalue()
    for chunk in (
        db.execute(
            stmt.order_by(ValidationResult.row_number, ValidationResult.rule_code).execution_options(yield_per=batch)
        )
        .scalars()
        .partitions(batch)
    ):
        buf.seek(0)
        buf.truncate()
        for r in chunk:
            writer.writerow(
                [
                    r.trade_id,
                    r.row_number,
                    r.asset_class,
                    r.regulator,
                    r.rule_code,
                    r.severity,
                    r.status,
                    r.explanation,
                    r.clause_ref or "",
                    r.citation_label or "",
                    "; ".join(f"{k}={v}" for k, v in (r.field_values or {}).items()),
                ]
            )
        yield buf.getvalue()
