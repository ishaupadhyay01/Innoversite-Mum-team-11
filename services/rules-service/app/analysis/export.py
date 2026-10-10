"""CSV export of analysis results with spreadsheet formula-injection protection."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator
from typing import Any

_DANGEROUS_PREFIX = ("=", "+", "-", "@", "\t", "\r")
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

MATRIX_COLUMNS = [
    "Trade_ID",
    "Asset_Class",
    "Regulator",
    "Rule_ID",
    "Rule_Description",
    "Status",
    "Affected_Field",
    "Actual_Value",
    "Expected_Condition",
    "Explanation",
    "Rule_Source",
    "Severity",
    "Failure_Category",
]


def safe_cell(value: Any) -> str:
    """Neutralise cells a spreadsheet would interpret as a formula.

    Cells starting with ``= + - @`` (or tab/CR) are prefixed with ``'``,
    except plain numbers such as ``-99.9`` which are data, not formulas.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if text.startswith(_DANGEROUS_PREFIX) and not _NUMBER_RE.match(text):
        return "'" + text
    return text


def _actual_value_text(values: dict[str, Any]) -> str:
    return "; ".join(f"{k}={'' if v is None else v}" for k, v in values.items())


def matrix_row(r: dict[str, Any]) -> list[str]:
    return [
        safe_cell(r["trade_id"]),
        safe_cell(r["asset_class"]),
        safe_cell(r["regulator"]),
        safe_cell(r["rule_id"]),
        safe_cell(r["rule_description"]),
        safe_cell(r["status"]),
        safe_cell(", ".join(r.get("affected_fields") or [])),
        safe_cell(_actual_value_text(r.get("actual_values") or {})),
        safe_cell(r.get("expected_condition")),
        safe_cell(r.get("explanation")),
        safe_cell(r.get("rule_source")),
        safe_cell(r.get("severity")),
        safe_cell(r.get("category")),
    ]


def iter_matrix_csv(rows: Iterable[dict[str, Any]]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MATRIX_COLUMNS)
    yield buffer.getvalue()
    for r in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(matrix_row(r))
        yield buffer.getvalue()


def summary_csv(summary: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Section", "Key", "Pass", "Fail", "Not_Applicable", "Error", "Impacted_Trades"])
    counts = summary.get("status_counts", {})
    writer.writerow(
        [
            "Totals",
            "All rules",
            counts.get("PASS", 0),
            counts.get("FAIL", 0),
            counts.get("NOT_APPLICABLE", 0),
            counts.get("ERROR", 0),
            summary.get("unique_impacted_trades", 0),
        ]
    )
    combined = summary.get("combined")
    if combined:
        c = combined["status_counts"]
        writer.writerow(
            [
                "Trades (rules combined with AND)",
                safe_cell(combined["expression"]),
                c.get("PASS", 0),
                c.get("FAIL", 0),
                c.get("NOT_APPLICABLE", 0),
                c.get("ERROR", 0),
                combined.get("non_compliant_trades", 0),
            ]
        )
    for reg in summary.get("by_regulator", []):
        writer.writerow(
            [
                "Regulator",
                safe_cell(reg["regulator"]),
                reg["pass"],
                reg["fail"],
                reg["not_applicable"],
                reg["error"],
                reg["impacted_trades"],
            ]
        )
    for rule in summary.get("by_rule", []):
        writer.writerow(["Rule", safe_cell(rule["rule_id"]), rule["pass"], rule["fail"], rule["not_applicable"], rule["error"], ""])
    return buffer.getvalue()


VERDICT_COLUMNS = [
    "Trade_ID",
    "Asset_Class",
    "Overall_Status",
    "Compliant",
    "Combined_Logic",
    "Rules_Evaluated",
    "Failed_Rules",
    "Error_Rules",
    "Passed_Rules",
    "Not_Applicable_Rules",
    "Reason",
    "Failure_Details",
]


def verdict_csv(verdicts: Iterable[dict[str, Any]], expression: str) -> str:
    """One row per trade: the selected rules combined with AND."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(VERDICT_COLUMNS)
    for v in verdicts:
        details = " | ".join(f"{f['rule_id']}: {f.get('explanation') or ''}".strip() for f in v["failures"])
        writer.writerow(
            [
                safe_cell(v["trade_id"]),
                safe_cell(v["asset_class"]),
                safe_cell(v["overall"]),
                "yes" if v["compliant"] else "no",
                safe_cell(expression),
                v["rules_evaluated"],
                safe_cell(", ".join(v["failed_rule_ids"])),
                safe_cell(", ".join(v["error_rule_ids"])),
                safe_cell(", ".join(v["passed_rule_ids"])),
                safe_cell(", ".join(v["not_applicable_rule_ids"])),
                safe_cell(v["reason"]),
                safe_cell(details),
            ]
        )
    return buffer.getvalue()
