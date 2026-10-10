"""Transparent configuration-normalisation layer for supplied rule files.

The source JSON files are never modified. When a rule is loaded, a *copy* of
its logic goes through the generic normalisers below, and every change is
recorded as a note that is shown next to the rule in the API and UI.

Generic normalisers (apply to any rule, never keyed by rule id):

``regex_field_reference``
    ``{"regex": ["Underlying_ISIN", "^...$"]}`` passes the bare field *name*
    as the value to test. If the first argument is a string literal that
    exactly names a known trade field, it is rewritten to
    ``{"var": "Underlying_ISIN"}``. (Testing the literal string
    "Underlying_ISIN" against an ISIN pattern can never be the intent.)

``regex_anchor_dedup``
    A trailing ``$$`` end anchor is collapsed to ``$``. In Python ``re`` the
    two are equivalent; the rewrite only makes the pattern canonical.

``field_alias``
    Field names listed in the overlay's ``field_aliases`` (for example
    ``Execution_Timestamp`` -> ``Timestamp``, the column actually present in
    the trade CSV) are rewritten.

Declarative overlay (``config/rules_overlay.json``):

``applies_when``
    Data, not code: an explicit applicability expression for a rule whose
    supplied logic cannot express "this rule does not apply to this trade".
    Used only when the source rule does not declare ``applies_when`` itself.
    Each entry carries a written rationale which is displayed in the UI.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .expressions import operator_of


@dataclass
class Overlay:
    field_aliases: dict[str, str] = field(default_factory=dict)
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    source: str | None = None

    @classmethod
    def load(cls, path: Path | None) -> Overlay:
        if path is None or not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            field_aliases=dict(data.get("field_aliases") or {}),
            rules=dict(data.get("rules") or {}),
            source=path.name,
        )


def _dedup_anchor(pattern: str) -> str:
    """Collapse a run of trailing end anchors ('$$' -> '$'), respecting an escaped literal '\\$'."""
    stripped = pattern.rstrip("$")
    run = len(pattern) - len(stripped)
    if run <= 1:
        return pattern
    backslashes = len(stripped) - len(stripped.rstrip("\\"))
    if backslashes % 2 == 1:
        return stripped + "$$"  # literal '\\$' followed by a single anchor
    return stripped + "$"


def normalize_logic(logic: Any, known_fields: set[str], aliases: dict[str, str] | None = None) -> tuple[Any, list[str]]:
    """Return (normalised copy of logic, notes)."""
    aliases = aliases or {}
    notes: list[str] = []

    def walk(expr: Any) -> Any:
        if isinstance(expr, list):
            return [walk(e) for e in expr]
        if not isinstance(expr, dict):
            return expr
        node = operator_of(expr)
        assert node is not None
        op, args = node
        args = [copy.deepcopy(a) for a in args]
        if op == "var" and args and isinstance(args[0], str) and args[0] in aliases:
            target = aliases[args[0]]
            notes.append(f"field_alias: var {args[0]!r} rewritten to {target!r} (column present in the trade data)")
            args[0] = target
            return {"var": args if len(args) > 1 else args[0]}
        if op == "regex" and len(args) >= 2:
            first = args[0]
            if isinstance(first, str):
                name = aliases.get(first, first)
                if name in known_fields:
                    notes.append(
                        f"regex_field_reference: regex value {first!r} is a bare field name; "
                        f'evaluated as the field value {{"var": "{name}"}}'
                    )
                    args[0] = {"var": name}
            if isinstance(args[1], str):
                fixed = _dedup_anchor(args[1])
                if fixed != args[1]:
                    notes.append(
                        f"regex_anchor_dedup: pattern {args[1]!r} normalised to {fixed!r} (duplicated end anchor; equivalent in Python re)"
                    )
                    args[1] = fixed
        new_args = [walk(a) for a in args]
        if op == "var" and len(new_args) == 1:
            return {"var": new_args[0]}
        return {op: new_args}

    return walk(logic), notes


def normalize_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise the reporting JSON Schema: ``$$schema`` key and ``$$`` pattern anchors."""
    notes: list[str] = []
    out = copy.deepcopy(schema)
    if "$$schema" in out and "$schema" not in out:
        out["$schema"] = out.pop("$$schema")
        notes.append("schema: non-standard key '$$schema' treated as '$schema'")
    for name, prop in (out.get("properties") or {}).items():
        pattern = prop.get("pattern")
        if isinstance(pattern, str):
            fixed = _dedup_anchor(pattern)
            if fixed != pattern:
                prop["pattern"] = fixed
                notes.append(f"schema: {name}.pattern {pattern!r} normalised to {fixed!r} (duplicated end anchor)")
    return out, notes
