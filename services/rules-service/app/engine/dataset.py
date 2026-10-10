"""Trade dataset loading (pandas), schema-driven type coercion and schema validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft7Validator, FormatChecker

from .normalization import normalize_schema

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


class DatasetError(ValueError):
    pass


@dataclass
class TradeDataset:
    name: str
    columns: list[str]
    trades: list[dict[str, Any]]
    raw_rows: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.trades)

    def by_id(self, id_field: str = "Trade_ID") -> dict[str, dict[str, Any]]:
        return {str(t.get(id_field)): t for t in self.trades}


@dataclass
class ReportingSchema:
    schema: dict[str, Any]
    notes: list[str]
    source: str

    @property
    def properties(self) -> dict[str, Any]:
        return self.schema.get("properties") or {}

    @property
    def required(self) -> list[str]:
        return list(self.schema.get("required") or [])

    @property
    def field_names(self) -> set[str]:
        return set(self.properties)

    @classmethod
    def load(cls, path: Path) -> ReportingSchema:
        raw = json.loads(path.read_text(encoding="utf-8"))
        schema, notes = normalize_schema(raw)
        return cls(schema=schema, notes=notes, source=path.name)


def _types(prop: dict[str, Any]) -> list[str]:
    t = prop.get("type")
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)] if t else []


def coerce_value(raw: str, prop: dict[str, Any] | None) -> tuple[Any, str | None]:
    """Convert a CSV string into the schema type. Returns (value, warning_or_None)."""
    value = (raw or "").strip()
    if value == "":
        return None, None
    types = _types(prop or {})
    if "integer" in types:
        if _INT_RE.match(value):
            return int(value), None
        if _FLOAT_RE.match(value) and float(value).is_integer():
            return int(float(value)), None
        return value, f"expected an integer, got {value!r}"
    if "number" in types:
        if _FLOAT_RE.match(value):
            number = float(value)
            return number, None
        return value, f"expected a number, got {value!r}"
    return value, None


def load_trades(path: Path, schema: ReportingSchema | None = None) -> TradeDataset:
    if not path.exists():
        raise DatasetError(f"Trade file {path.name!r} not found")
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")
    except Exception as exc:  # pandas raises several parser exception types
        raise DatasetError(f"Trade file {path.name!r} could not be parsed as CSV: {exc}") from exc
    frame.columns = [str(c).strip() for c in frame.columns]
    columns = list(frame.columns)
    warnings: list[str] = []
    if schema is not None:
        missing = [c for c in schema.required if c not in columns]
        if missing:
            warnings.append(f"required schema columns missing from the CSV: {', '.join(missing)}")
        extra = [c for c in columns if c not in schema.properties]
        if extra:
            warnings.append(f"columns not described by the schema (kept as text): {', '.join(extra)}")
    raw_rows: list[dict[str, str]] = [{k: str(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]
    trades: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_rows, start=2):
        trade: dict[str, Any] = {}
        for col, raw in row.items():
            prop = schema.properties.get(col) if schema else None
            value, warning = coerce_value(raw, prop)
            if warning:
                warnings.append(f"line {idx} ({row.get('Trade_ID', '?')}): {col} {warning}")
            trade[col] = value
        trades.append(trade)
    if "Trade_ID" in columns:
        ids = [t.get("Trade_ID") for t in trades]
        dupes = sorted({i for i in ids if ids.count(i) > 1 and i is not None})
        if dupes:
            warnings.append(f"duplicate Trade_ID values: {', '.join(map(str, dupes[:10]))}")
    return TradeDataset(name=path.name, columns=columns, trades=trades, raw_rows=raw_rows, warnings=warnings)


def _format_checker() -> FormatChecker:
    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def _is_datetime(value: object) -> bool:
        if not isinstance(value, str):
            return True
        if "T" not in value and " " not in value:
            raise ValueError("not an ISO-8601 date-time")
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True

    @checker.checks("date", raises=ValueError)
    def _is_date(value: object) -> bool:
        if not isinstance(value, str):
            return True
        date.fromisoformat(value)
        return True

    return checker


@dataclass
class SchemaFinding:
    trade_id: str
    field: str
    check: str  # required | type | enum | pattern | minimum | format | ...
    message: str
    value: Any


def validate_against_schema(dataset: TradeDataset, schema: ReportingSchema) -> list[SchemaFinding]:
    """Optional reporting-schema validation (distinct from rule-based findings)."""
    validator = Draft7Validator(schema.schema, format_checker=_format_checker())
    findings: list[SchemaFinding] = []
    for trade in dataset.trades:
        instance = {k: v for k, v in trade.items() if v is not None or "null" in _types(schema.properties.get(k, {}))}
        trade_id = str(trade.get("Trade_ID"))
        for error in sorted(validator.iter_errors(instance), key=lambda e: (list(e.path), e.validator)):
            if error.validator == "required":
                field_name = re.findall(r"'([^']+)' is a required property", error.message)
                name = field_name[0] if field_name else "?"
                findings.append(SchemaFinding(trade_id, name, "required", f"{name} is required but missing", None))
                continue
            name = ".".join(str(p) for p in error.path) or "?"
            findings.append(SchemaFinding(trade_id, name, str(error.validator), f"{name}: {error.message}", trade.get(name)))
    return findings
