"""Explanation layer: *why* an expression evaluated to false for a record.

The explanation walks the expression with the same semantics as the
evaluator (short-circuit ``and``, branch selection for ``if``) and describes
the specific sub-expression(s) that failed, together with the actual field
values. Nothing here is rule-specific.

Failure categories (used by gap analysis):

* ``missing_value``      – a required field is absent/empty
* ``invalid_format``     – a value does not match a regex
* ``value_not_allowed``  – a value is not in an allowed list
* ``negative_value``     – a numeric field is negative where it must not be
* ``numeric_constraint`` – other numeric bound violated (e.g. quantity 0)
* ``date_constraint``    – a date-derived comparison failed
* ``value_mismatch``     – equality / other comparison failed
* ``constant``           – the rule branch is a constant false
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .expressions import (
    evaluate,
    fields_in,
    iso_date_to_number,
    operator_of,
    to_number,
    truthy,
)
from .render import render


@dataclass
class Reason:
    message: str
    fields: list[str]
    category: str
    expected: str
    conditional: str | None = None  # the triggering condition when inside an if-branch

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "fields": self.fields,
            "category": self.category,
            "expected": self.expected,
            "conditional": self.conditional,
        }


def _fmt(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def _describe(expr: Any, data: dict[str, Any]) -> str:
    """Name of a value expression for messages: the field name, or the rendered expression
    plus the underlying field values."""
    node = operator_of(expr) if isinstance(expr, dict) else None
    if node and node[0] == "var":
        return str(node[1][0])
    text = render(expr, False)
    fields = fields_in(expr)
    if fields:
        values = ", ".join(f"{f} = {_fmt(data.get(f))}" for f in fields)
        return f"{text} (from {values})"
    return text


def _uses_date(expr: Any, data: dict[str, Any]) -> bool:
    node = operator_of(expr) if isinstance(expr, dict) else None
    if node is None:
        return False
    op, args = node
    if op == "toNumber":
        try:
            inner = evaluate(args[0], data)
        except Exception:  # noqa: BLE001 - only used for categorisation
            return False
        return isinstance(inner, str) and iso_date_to_number(inner) is not None
    return any(_uses_date(a, data) for a in args if isinstance(a, (dict, list)))


def why_false(expr: Any, data: dict[str, Any], conditional: str | None = None) -> list[Reason]:
    node = operator_of(expr) if isinstance(expr, dict) else None
    if node is None:
        return [Reason(f"Rule branch is the constant {render(expr)}", [], "constant", render(expr), conditional)]
    op, args = node

    if op == "and":
        for a in args:
            if not truthy(evaluate(a, data)):
                return why_false(a, data, conditional)
        return []
    if op == "or":
        reasons: list[Reason] = []
        for a in args:
            reasons.extend(why_false(a, data, conditional))
        return reasons
    if op in {"if", "?:"}:
        i = 0
        while i + 1 < len(args):
            cond = args[i]
            if truthy(evaluate(cond, data)):
                return why_false(args[i + 1], data, _condition_text(cond, data, True))
            i += 2
        if i < len(args):
            negated = "; ".join(_condition_text(args[j], data, False) for j in range(0, i, 2))
            return why_false(args[i], data, negated or conditional)
        return [Reason("No branch of the conditional applied", fields_in(expr), "constant", render(expr), conditional)]
    if op in {"not", "!"}:
        inner = args[0]
        fields = fields_in(inner)
        values = ", ".join(f"{f} = {_fmt(data.get(f))}" for f in fields)
        return [
            Reason(
                f"{render(inner)} must not hold, but it does" + (f" ({values})" if values else ""),
                fields,
                "value_mismatch",
                render(expr),
                conditional,
            )
        ]
    if op in {"var", "!!"}:
        target = args[0] if op == "!!" else expr
        name = _describe(target, data)
        value = evaluate(target, data)
        if value is None:
            return [Reason(f"{name} is missing", fields_in(target), "missing_value", f"{name} is present", conditional)]
        return [
            Reason(
                f"{name} is {_fmt(value)}, which counts as empty",
                fields_in(target),
                "missing_value",
                f"{name} is present",
                conditional,
            )
        ]
    if op in {">", ">=", "<", "<="} or op in {"==", "!=", "===", "!=="}:
        return [_comparison_reason(op, args, data, conditional, expr)]
    if op == "in":
        needle, haystack = args[0], args[1]
        name = _describe(needle, data)
        value = evaluate(needle, data)
        allowed = evaluate(haystack, data)
        fields = fields_in(expr)
        if value is None:
            return [Reason(f"{name} is missing", fields, "missing_value", render(expr), conditional)]
        allowed_text = ", ".join(str(a) for a in allowed) if isinstance(allowed, list) else str(allowed)
        return [
            Reason(
                f"{name} {_fmt(value)} is not one of the allowed values ({allowed_text})",
                fields,
                "value_not_allowed",
                render(expr),
                conditional,
            )
        ]
    if op == "regex":
        name = _describe(args[0], data)
        value = evaluate(args[0], data)
        fields = fields_in(args[0])
        if value is None:
            return [Reason(f"{name} is missing", fields, "missing_value", render(expr), conditional)]
        return [
            Reason(
                f"{name} {_fmt(value)} does not match the required pattern /{args[1]}/",
                fields,
                "invalid_format",
                render(expr),
                conditional,
            )
        ]
    value = evaluate(expr, data)
    return [Reason(f"{render(expr)} evaluated to {_fmt(value)}", fields_in(expr), "value_mismatch", render(expr), conditional)]


def _comparison_reason(op: str, args: list[Any], data: dict[str, Any], conditional: str | None, expr: Any) -> Reason:
    left, right = args[0], args[1]
    lv, rv = evaluate(left, data), evaluate(right, data)
    fields = fields_in(expr)
    expected = render(expr)
    # Put the field-bearing side first in the message.
    subject, subject_val, other_val = (left, lv, rv) if fields_in(left) or not fields_in(right) else (right, rv, lv)
    name = _describe(subject, data)
    if lv is None or rv is None:
        missing_side = left if lv is None else right
        return Reason(
            f"{_describe(missing_side, data)} is missing, so {expected} cannot hold",
            fields,
            "missing_value",
            expected,
            conditional,
        )
    if op in {"==", "===", "!=", "!=="}:
        relation = "must equal" if op in {"==", "==="} else "must differ from"
        return Reason(f"{name} is {_fmt(subject_val)} but {relation} {_fmt(other_val)}", fields, "value_mismatch", expected, conditional)
    if _uses_date(expr, data):
        category = "date_constraint"
    else:
        number = to_number(subject_val)
        category = "negative_value" if number is not None and number < 0 else "numeric_constraint"
    return Reason(f"{name} is {_fmt(subject_val)}, which fails {expected}", fields, category, expected, conditional)


def _condition_text(cond: Any, data: dict[str, Any], held: bool) -> str:
    fields = fields_in(cond)
    values = ", ".join(f"{f} = {_fmt(data.get(f))}" for f in fields)
    text = render(cond)
    status = "holds" if held else "does not hold"
    return f"{text} {status}" + (f" ({values})" if values else "")
