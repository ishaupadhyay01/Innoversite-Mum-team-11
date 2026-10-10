"""Human-readable explanations ("explanation layer"): turn a failing JSONLogic tree into a sentence
such as  "Price (-99.9) must be ≥ 0"  or  "Counterparty_LEI is required but is missing"."""

from __future__ import annotations

import json
from typing import Any

from .jsonlogic import Data, JsonLogic, truthy
from .operations import resolve_field_or_value

SYMBOLS = {
    ">=": "≥",
    "<=": "≤",
    ">": ">",
    "<": "<",
    "==": "equal",
    "===": "equal",
    "!=": "differ from",
    "!==": "differ from",
}


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "missing"
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return json.dumps(value) if isinstance(value, (list, dict)) else str(value)


def operand(engine: JsonLogic, node: Any, data: Data) -> str:
    if engine.is_logic(node) and "var" in node:
        name = node["var"][0] if isinstance(node["var"], list) else node["var"]
        return f"{name} ({_fmt(engine.apply(node, data))})"
    if engine.is_logic(node):
        fields = engine.referenced_vars(node)
        value = engine.apply(node, data)
        if not fields:
            return _fmt(value)
        src = ", ".join(f"{f} ({_fmt(data.get(f))}" for f in fields)
        return f"{src} → {_fmt(value)})"
    return _fmt(node)


def describe(engine: JsonLogic, node: Any, data: Data, negated: bool = False) -> str:
    """Describe why ``node`` evaluated falsy (or truthy when negated)."""
    if not engine.is_logic(node):
        return f"constant {_fmt(node)} is {'true' if negated else 'false'}"
    op, args = next(iter(node.items()))
    args = args if isinstance(args, list) else [args]

    if op == "var":
        name = args[0]
        value = engine.apply(node, data)
        if value in (None, ""):
            return f"{name} is required but is missing"
        return f"{name} must not be {_fmt(value)}"
    if op == "!":
        return describe(engine, args[0], data, negated=not negated)
    if op == "and" and not negated:
        for a in args:
            if not truthy(engine.apply(a, data)):
                return describe(engine, a, data)
    if op == "or" and not negated:
        return "none of the alternatives hold: " + "; ".join(describe(engine, a, data) for a in args)
    if op in ("if", "?:"):
        i = 0
        while i < len(args) - 1:
            if truthy(engine.apply(args[i], data)):
                return describe(engine, args[i + 1], data, negated)
            i += 2
        return describe(engine, args[i], data, negated) if i < len(args) else "no branch matched"
    if op in (">=", "<=", ">", "<"):
        if len(args) == 3:
            return (
                f"{operand(engine, args[1], data)} must be between {operand(engine, args[0], data)} and "
                f"{operand(engine, args[2], data)}"
            )
        return f"{operand(engine, args[0], data)} must be {SYMBOLS[op]} {operand(engine, args[1], data)}"
    if op in ("==", "==="):
        return f"{operand(engine, args[0], data)} must equal {operand(engine, args[1], data)}"
    if op in ("!=", "!=="):
        return f"{operand(engine, args[0], data)} must differ from {operand(engine, args[1], data)}"
    if op == "in":
        hay = engine.apply(args[1], data)
        if isinstance(hay, list):
            return f"{operand(engine, args[0], data)} must be one of {', '.join(map(str, hay))}"
        return f"{operand(engine, args[1], data)} must contain {operand(engine, args[0], data)}"
    if op == "regex":
        raw = args[0]
        name = raw if isinstance(raw, str) and raw in data else None
        value = resolve_field_or_value(engine, raw, data)
        label = name or (operand(engine, raw, data) if engine.is_logic(raw) else "value")
        if value in (None, ""):
            return f"{label} is required but is missing"
        return f"{label} ({_fmt(value)}) must match pattern {engine.apply(args[1], data)}"
    if op in ("missing", "missing_some"):
        return f"missing required field(s): {', '.join(engine.apply(node, data))}"
    if op in ("isValidLEI", "isValidISIN", "isDate"):
        what = {
            "isValidLEI": "a valid LEI (ISO 17442 checksum)",
            "isValidISIN": "a valid ISIN (ISO 6166)",
            "isDate": "a valid ISO-8601 date",
        }[op]
        return f"{operand(engine, args[0], data)} must be {what}"
    return f"condition {json.dumps(node)} is {'true' if negated else 'false'}"


def describe_condition(engine: JsonLogic, node: Any, data: Data) -> str:
    """Positive phrasing of a condition that held, e.g. "Asset_Class ('FX') equals 'FX'"."""
    if engine.is_logic(node):
        op, args = next(iter(node.items()))
        args = args if isinstance(args, list) else [args]
        if op in ("==", "===") and len(args) == 2:
            return f"{operand(engine, args[0], data)} equals {operand(engine, args[1], data)}"
        if op in ("!=", "!==") and len(args) == 2:
            return f"{operand(engine, args[0], data)} is not {operand(engine, args[1], data)}"
    return describe(engine, node, data, negated=True)
