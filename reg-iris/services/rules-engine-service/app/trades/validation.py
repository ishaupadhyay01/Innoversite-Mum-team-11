"""File-level validation of an uploaded trade CSV against the reporting schema (vectorised, chunked).

Structural problems (unreadable, empty, missing required columns) make the dataset INVALID.
Field-level problems are reported as warnings: the rules engine still runs and explains them per rule.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .schema import ReportingSchema

MAX_SAMPLE_ISSUES = 200


@dataclass
class DatasetReport:
    status: str = "VALID"  # VALID | VALID_WITH_WARNINGS | INVALID
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    duplicate_trade_ids: int = 0
    issue_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    sample_issues: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _field_issues(df: pd.DataFrame, schema: ReportingSchema) -> dict[str, pd.Series]:
    """Return {"Field:issue": boolean mask of offending rows}."""
    out: dict[str, pd.Series] = {}
    for spec in schema.fields:
        if spec.name not in df.columns:
            continue
        col = df[spec.name].astype(str).str.strip()
        empty = col.eq("")
        if spec.required and not spec.nullable:
            out[f"{spec.name}:required"] = empty
        present = ~empty
        if spec.enum:
            out[f"{spec.name}:enum"] = present & ~col.isin([str(e) for e in spec.enum])
        if spec.pattern:
            out[f"{spec.name}:pattern"] = present & ~col.str.fullmatch(spec.pattern.strip("^$"), na=False)
        if spec.base_type in ("number", "integer"):
            num = pd.to_numeric(col.where(present), errors="coerce")
            out[f"{spec.name}:type"] = present & num.isna()
            if spec.base_type == "integer":
                out[f"{spec.name}:integer"] = present & num.notna() & (num % 1 != 0)
            if spec.minimum is not None:
                out[f"{spec.name}:minimum"] = present & num.notna() & (num < spec.minimum)
        if spec.fmt in ("date-time", "date"):
            parsed = pd.to_datetime(
                col.where(present),
                errors="coerce",
                utc=True,
                format="ISO8601" if spec.fmt == "date-time" else "%Y-%m-%d",
            )
            out[f"{spec.name}:format"] = present & parsed.isna()
    return out


def validate_trade_csv(path: Path, schema: ReportingSchema, chunk_size: int = 50_000) -> DatasetReport:
    report = DatasetReport()
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    seen_ids: set[str] = set()
    try:
        reader = pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=chunk_size, encoding="utf-8-sig")
        for chunk_no, df in enumerate(reader):
            if chunk_no == 0:
                report.columns = list(df.columns)
                report.missing_columns = [c for c in schema.required if c not in df.columns]
                report.extra_columns = [c for c in df.columns if c not in schema.names]
                if report.missing_columns:
                    report.errors.append(f"Missing required column(s): {', '.join(report.missing_columns)}")
                    break
            base = chunk_no * chunk_size
            if "Trade_ID" in df.columns:
                for tid in df["Trade_ID"]:
                    if tid in seen_ids:
                        report.duplicate_trade_ids += 1
                    seen_ids.add(tid)
            for key, mask in _field_issues(df, schema).items():
                n = int(mask.sum())
                if not n:
                    continue
                fname, issue = key.split(":")
                counts[fname][issue] += n
                for idx in mask[mask].index[: max(0, MAX_SAMPLE_ISSUES - len(report.sample_issues))]:
                    report.sample_issues.append(
                        {
                            "row": base + int(idx) + 2,
                            "trade_id": df.at[idx, "Trade_ID"] if "Trade_ID" in df.columns else None,
                            "field": fname,
                            "issue": issue,
                            "value": df.at[idx, fname],
                        }
                    )
            report.row_count += len(df)
    except UnicodeDecodeError:
        report.errors.append("File is not valid UTF-8 text")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        report.errors.append(f"CSV could not be parsed: {exc}")

    report.issue_counts = {k: dict(v) for k, v in counts.items()}
    if report.row_count == 0 and not report.errors:
        report.errors.append("CSV contains no data rows")
    if report.duplicate_trade_ids:
        counts["Trade_ID"]["duplicate"] += report.duplicate_trade_ids
        report.issue_counts = {k: dict(v) for k, v in counts.items()}
    report.status = "INVALID" if report.errors else ("VALID_WITH_WARNINGS" if report.issue_counts else "VALID")
    return report
