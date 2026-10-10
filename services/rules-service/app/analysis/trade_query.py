"""Deterministic parser for a documented set of trade-data questions.

Regulatory *document* questions go to Elasticsearch. Questions about the
*trade data* ("Which trades are missing a Counterparty LEI?") are structured
filters, not keyword search. This parser recognises a small, documented set
of patterns and turns them into filters; anything else is reported as
unsupported rather than guessed.

Supported patterns (case-insensitive):

1. ``... missing (a|an|the) <field>`` / ``... without <field>`` /
   ``... (do not|don't) have (a|an) <field>``
2. ``<asset class> trades ...`` combined with any other pattern
3. ``... <field> is negative`` / ``negative <field>``
4. ``... <field> (that is )?not in the approved list`` (uses the schema enum)
5. ``... executed (before|after|on or after|on or before) <YYYY-MM-DD>``
6. ``how many ...`` returns only the count

Field names are matched against the reporting schema, ignoring case,
underscores and spacing; the final word may match a field suffix
("LEI" -> Counterparty_LEI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from iris_shared.text import normalize_inline

from ..engine.dataset import ReportingSchema, TradeDataset

SUPPORTED_PATTERNS = [
    "Which trades are missing a <field>?",
    "Show <asset class> trades that do not have a <field>.",
    "List trades where the <numeric field> is negative.",
    "How many trades use a <field> that is not in the approved list?",
    "Which trades were executed before <YYYY-MM-DD>?",
]

_DATE_RE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")


@dataclass
class Condition:
    field: str
    op: str  # missing | negative | not_in | before | after | on_or_after | on_or_before | equals
    value: Any = None

    def describe(self) -> str:
        if self.op == "missing":
            return f"{self.field} is missing"
        if self.op == "negative":
            return f"{self.field} < 0"
        if self.op == "not_in":
            return f"{self.field} not in {', '.join(self.value)}"
        if self.op == "equals":
            return f"{self.field} = {self.value}"
        symbol = {"before": "<", "after": ">", "on_or_after": ">=", "on_or_before": "<="}[self.op]
        return f"{self.field} {symbol} {self.value}"


@dataclass
class ParsedQuery:
    matched: bool
    conditions: list[Condition] = field(default_factory=list)
    count_only: bool = False
    message: str = ""


def _canon(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve_field(phrase: str, schema: ReportingSchema) -> str | None:
    target = _canon(phrase)
    if not target:
        return None
    names = sorted(schema.field_names)
    for name in names:
        if _canon(name) == target:
            return name
    # suffix match: "LEI" -> Counterparty_LEI, "ISIN" -> Underlying_ISIN, "maturity date" -> Maturity_Date
    candidates = [n for n in names if _canon(n).endswith(target) or _canon(n).startswith(target)]
    return candidates[0] if len(candidates) == 1 else None


def _find_field_after(keyword_re: str, text: str, schema: ReportingSchema) -> str | None:
    m = re.search(keyword_re + r"\s+(?:a|an|the)?\s*([a-z_ ]+?)(?:\?|\.|,|$| that | which | and )", text, re.I)
    if not m:
        return None
    words = m.group(1).strip().split()
    # try longest phrase first: "counterparty lei", then "lei"
    for start in range(len(words)):
        found = resolve_field(" ".join(words[start:]), schema)
        if found:
            return found
    for end in range(len(words), 0, -1):
        found = resolve_field(" ".join(words[:end]), schema)
        if found:
            return found
    return None


def parse_trade_query(question: str, schema: ReportingSchema) -> ParsedQuery:
    text = normalize_inline(question)
    lower = text.lower()
    if "trade" not in lower:
        return ParsedQuery(False, message="Not a trade-data question (no mention of trades).")

    conditions: list[Condition] = []
    asset_enum = (schema.properties.get("Asset_Class") or {}).get("enum") or []
    for asset in asset_enum:
        if re.search(rf"\b{re.escape(asset)}s?\b", text, re.I):
            conditions.append(Condition("Asset_Class", "equals", asset))
            break

    missing_field = (
        _find_field_after(r"\bmissing", text, schema)
        or _find_field_after(r"\bwithout", text, schema)
        or _find_field_after(r"\b(?:do not|don't|does not|doesn't) have", text, schema)
    )
    if missing_field:
        conditions.append(Condition(missing_field, "missing"))

    m = re.search(r"\b(\w[\w ]*?)\s+is\s+negative\b", text, re.I) or re.search(r"\bnegative\s+(\w+)", text, re.I)
    if m:
        words = m.group(1).split()
        fld = None
        for start in range(len(words)):
            fld = resolve_field(" ".join(words[start:]), schema)
            if fld:
                break
        if fld:
            conditions.append(Condition(fld, "negative"))

    m = re.search(r"\b(?:a|an|the)?\s*(\w+)\s+(?:that\s+is\s+|which\s+is\s+)?not\s+in\s+the\s+approved\s+list", text, re.I)
    if m:
        fld = resolve_field(m.group(1), schema)
        enum = (schema.properties.get(fld) or {}).get("enum") if fld else None
        explicit = re.search(r"\(([A-Z]{3}(?:\s*,\s*[A-Z]{3})+)\)", text)
        allowed = [v.strip() for v in explicit.group(1).split(",")] if explicit else enum
        if fld and allowed:
            conditions.append(Condition(fld, "not_in", list(allowed)))

    m = re.search(r"\bexecuted\s+(on or before|on or after|before|after)\s+(\S+)", text, re.I)
    if m:
        dm = _DATE_RE.search(m.group(2))
        if dm:
            d = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            op = m.group(1).lower().replace(" ", "_")
            conditions.append(Condition("Timestamp", op, d.isoformat()))

    if not conditions or (len(conditions) == 1 and conditions[0].field == "Asset_Class" and conditions[0].op == "equals"):
        return ParsedQuery(
            False,
            message="Question not recognised. Supported patterns: " + " | ".join(SUPPORTED_PATTERNS),
        )
    return ParsedQuery(True, conditions, count_only=lower.startswith("how many"))


def _matches(trade: dict[str, Any], cond: Condition) -> bool:
    value = trade.get(cond.field)
    if cond.op == "missing":
        return value is None or str(value).strip() == ""
    if cond.op == "equals":
        return value is not None and str(value).lower() == str(cond.value).lower()
    if cond.op == "negative":
        return isinstance(value, (int, float)) and value < 0
    if cond.op == "not_in":
        return value is not None and str(value) not in cond.value
    if value is None:
        return False
    day = str(value)[:10]
    if cond.op == "before":
        return day < cond.value
    if cond.op == "after":
        return day > cond.value
    if cond.op == "on_or_after":
        return day >= cond.value
    if cond.op == "on_or_before":
        return day <= cond.value
    return False


def run_trade_query(parsed: ParsedQuery, dataset: TradeDataset) -> list[dict[str, Any]]:
    return [t for t in dataset.trades if all(_matches(t, c) for c in parsed.conditions)]
