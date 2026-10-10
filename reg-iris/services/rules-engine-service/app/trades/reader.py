"""Stream trades from CSV in chunks, coerced to the reporting schema's types for rule evaluation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from .schema import ReportingSchema


def _coerce(value: str, base_type: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    if base_type in ("number", "integer"):
        try:
            num = float(value)
        except ValueError:
            return value  # keep raw text; rules will explain it isn't numeric
        return int(num) if base_type == "integer" and num.is_integer() else num
    return value


def iter_trade_chunks(
    path: Path, schema: ReportingSchema, chunk_size: int, *, skip_rows: int = 0, max_rows: int | None = None
) -> Iterator[list[tuple[int, dict[str, Any]]]]:
    """Yield lists of (row_number, trade) — row_number is 1-based data row (excluding header)."""
    types = {f.name: f.base_type for f in schema.fields}
    skip = range(1, skip_rows + 1) if skip_rows else None
    reader = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        chunksize=chunk_size,
        encoding="utf-8-sig",
        skiprows=skip,
        nrows=max_rows,
    )
    row_no = skip_rows
    for df in reader:
        batch = []
        for record in df.to_dict(orient="records"):
            row_no += 1
            trade = {name: None for name in types}  # every schema field present (None if absent)
            trade.update({k: _coerce(v, types.get(k, "string")) for k, v in record.items()})
            batch.append((row_no, trade))
        yield batch
