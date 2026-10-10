"""Import and normalisation of ``doc_metadata.csv``.

Normalisations (all recorded as notes, never silent):

* **Effective dates** such as ``01-07-23`` are two-digit-year dates. The
  day/month order is inferred from the whole column: a component greater
  than 12 proves the order (the dataset contains ``15-01-21`` and
  ``30-11-22``, which can only be day-first). Two-digit years map to 2000–2069
  / 1970–1999.
* **Regulator labels**: Unicode hyphen variants are folded to ``-``
  (the dataset uses a non-breaking hyphen in ``Dodd‑Frank``).
* **Version families**: ``parent_doc_id`` chains are followed to their root
  so every version of a regulation shares one document family, even when a
  parent id refers to an older ancestor.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from iris_shared.text import normalize_inline, normalize_label

REQUIRED_COLUMNS = {
    "document_id",
    "file_name",
    "regulator",
    "jurisdiction",
    "effective_date",
    "category",
    "version",
    "upload_timestamp",
    "parent_doc_id",
}

_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SHORT_DATE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$")
_VERSION_SUFFIX = re.compile(r"[_\-\s]+v\d+(?:[._]\d+)*$", re.IGNORECASE)


class MetadataError(ValueError):
    pass


@dataclass
class MetadataRow:
    source_id: int
    file_name: str
    regulator: str
    jurisdiction: str
    effective_date: date | None
    category: str
    version_label: str
    uploaded_at: datetime
    parent_source_id: int | None
    raw: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def family_key(self) -> str:
        return family_key_for(self.file_name)


def family_key_for(file_name: str) -> str:
    """``MiFID_II_2023_v2.pdf`` -> ``MiFID_II_2023``; used to group versions of one document."""
    stem = Path(file_name).stem
    return _VERSION_SUFFIX.sub("", stem) or stem


def title_for(file_name: str) -> str:
    return normalize_inline(family_key_for(file_name).replace("_", " "))


def _year(two_or_four: str) -> int:
    y = int(two_or_four)
    if len(two_or_four) == 4:
        return y
    return 2000 + y if y < 70 else 1900 + y


def infer_day_first(values: list[str]) -> tuple[bool, str]:
    """Decide day/month order for short dates from evidence in the whole column."""
    day_first_evidence: list[str] = []
    month_first_evidence: list[str] = []
    for value in values:
        m = _SHORT_DATE.match(value.strip())
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            day_first_evidence.append(value)
        elif b > 12 >= a:
            month_first_evidence.append(value)
    if day_first_evidence and month_first_evidence:
        raise MetadataError(
            "Inconsistent date formats in effective_date column: "
            f"{day_first_evidence[0]!r} is day-first but {month_first_evidence[0]!r} is month-first"
        )
    if month_first_evidence:
        return False, f"month-first (MM-DD-YY) inferred from {month_first_evidence[0]!r}"
    if day_first_evidence:
        unique = list(dict.fromkeys(day_first_evidence))
        return True, f"day-first (DD-MM-YY) inferred from {', '.join(repr(v) for v in unique[:3])}"
    return True, "day-first (DD-MM-YY) assumed: no unambiguous value in column"


def normalize_date(value: str, day_first: bool = True) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    m = _ISO_DATE.match(value)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _SHORT_DATE.match(value)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        day, month = (a, b) if day_first else (b, a)
        try:
            return date(y, month, day)
        except ValueError as exc:
            raise MetadataError(f"Invalid date {value!r}: {exc}") from exc
    raise MetadataError(f"Unrecognised date format {value!r}")


def parse_timestamp(value: str) -> datetime:
    value = (value or "").strip()
    if not value:
        raise MetadataError("upload_timestamp is required")
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetadataError(f"Invalid upload_timestamp {value!r}") from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def parse_metadata_csv(text: str) -> tuple[list[MetadataRow], list[str], str]:
    """Parse the metadata CSV. Returns (rows, errors, date_convention_note).

    Rows with errors are excluded and reported; valid rows are still returned.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = {c.strip() for c in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise MetadataError(f"Metadata CSV is missing columns: {', '.join(sorted(missing))}")
    raw_rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    day_first, convention = infer_day_first([r["effective_date"] for r in raw_rows])

    rows: list[MetadataRow] = []
    errors: list[str] = []
    seen_ids: set[int] = set()
    for line_no, r in enumerate(raw_rows, start=2):
        try:
            source_id = int(r["document_id"])
            if source_id in seen_ids:
                raise MetadataError(f"duplicate document_id {source_id}")
            seen_ids.add(source_id)
            if not r["file_name"]:
                raise MetadataError("file_name is required")
            notes: list[str] = []
            regulator = normalize_label(r["regulator"])
            if regulator != r["regulator"]:
                notes.append(f"regulator label normalised from {r['regulator']!r} to {regulator!r}")
            effective = normalize_date(r["effective_date"], day_first)
            if effective and r["effective_date"] != effective.isoformat():
                notes.append(f"effective_date {r['effective_date']!r} interpreted as {effective.isoformat()} ({convention})")
            parent = int(r["parent_doc_id"]) if r["parent_doc_id"] else None
            rows.append(
                MetadataRow(
                    source_id=source_id,
                    file_name=r["file_name"],
                    regulator=regulator,
                    jurisdiction=normalize_label(r["jurisdiction"]),
                    effective_date=effective,
                    category=normalize_label(r["category"]),
                    version_label=normalize_label(r["version"]) or "v1.0",
                    uploaded_at=parse_timestamp(r["upload_timestamp"]),
                    parent_source_id=parent,
                    raw=r,
                    notes=notes,
                )
            )
        except (MetadataError, ValueError) as exc:
            errors.append(f"metadata line {line_no}: {exc}")
    return rows, errors, convention


def resolve_family_roots(rows: list[MetadataRow]) -> tuple[dict[int, int], list[str]]:
    """Map each row's source_id to the source_id of its family root (following parent chains)."""
    by_id = {r.source_id: r for r in rows}
    roots: dict[int, int] = {}
    errors: list[str] = []
    for row in rows:
        seen: list[int] = []
        current = row
        while current.parent_source_id is not None:
            if current.source_id in seen:
                errors.append(f"document_id {row.source_id}: cyclic parent chain {seen}")
                break
            seen.append(current.source_id)
            parent = by_id.get(current.parent_source_id)
            if parent is None:
                errors.append(
                    f"document_id {current.source_id}: parent_doc_id {current.parent_source_id} not found; "
                    "treated as the start of its own family"
                )
                break
            current = parent
        roots[row.source_id] = current.source_id
    return roots, errors


def import_order(rows: list[MetadataRow]) -> list[MetadataRow]:
    """Deterministic import order: by upload timestamp, then source id (parents before children)."""
    return sorted(rows, key=lambda r: (r.uploaded_at, r.source_id))
