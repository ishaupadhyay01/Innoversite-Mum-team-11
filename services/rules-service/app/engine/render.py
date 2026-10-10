"""Human-readable rendering of rule expressions (for explanations and the UI)."""

from __future__ import annotations

import json
from typing import Any

from .expressions import operator_of

_BOOLEAN_OPS = {"and", "or", "not", "!", "if", "?:"}
_COMPARISONS = {"==", "!=", "===", "!==", ">", ">=", "<", "<="}


def _literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def render(expr: Any, boolean_ctx: bool = True) -> str:
    """Render an expression as infix text.

    ``boolean_ctx`` marks positions where a bare value is used as a condition,
    so ``{"var": "X"}`` renders as ``X is present``.
    """
    if isinstance(expr, list):
        return "[" + ", ".join(render(e, False) for e in expr) + "]"
    node = operator_of(expr) if isinstance(expr, dict) else None
    if node is None:
        return _literal(expr)
    op, args = node
    if op == "var":
        name = str(args[0]) if args else "<record>"
        return f"{name} is present" if boolean_ctx else name
    if op in {"and", "or"}:
        joiner = " AND " if op == "and" else " OR "
        parts = []
        for a in args:
            text = render(a, True)
            inner = operator_of(a) if isinstance(a, dict) else None
            if inner and inner[0] in {"and", "or", "if", "?:"} and inner[0] != op:
                text = f"({text})"
            parts.append(text)
        return joiner.join(parts)
    if op in {"not", "!"}:
        return f"NOT ({render(args[0], True)})"
    if op == "!!":
        return f"{render(args[0], False)} is truthy"
    if op in {"if", "?:"}:
        out = []
        i = 0
        while i + 1 < len(args):
            prefix = "IF" if i == 0 else "ELSE IF"
            out.append(f"{prefix} {render(args[i], True)} THEN {render(args[i + 1], True)}")
            i += 2
        if i < len(args):
            out.append(f"ELSE {render(args[i], True)}")
        return " ".join(out)
    if op in _COMPARISONS:
        if len(args) == 3:
            return f"{render(args[0], False)} {op} {render(args[1], False)} {op} {render(args[2], False)}"
        return f"{render(args[0], False)} {op} {render(args[1], False)}"
    if op == "in":
        return f"{render(args[0], False)} IN {render(args[1], False)}"
    if op == "regex":
        return f"{render(args[0], False)} matches /{args[1]}/"
    if op == "substr":
        return "substr(" + ", ".join(render(a, False) for a in args) + ")"
    if op == "toNumber":
        return f"toNumber({render(args[0], False)})"
    if op == "missing":
        return "missing(" + ", ".join(render(a, False) for a in args) + ")"
    return f"{op}(" + ", ".join(render(a, False) for a in args) + ")"
