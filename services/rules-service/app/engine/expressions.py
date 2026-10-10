"""Safe, generic interpreter for JSONLogic-style rule expressions.

No ``eval``/``exec`` is used. Expressions are plain JSON values; operators
are looked up in a fixed registry. Adding a new rule never requires Python
changes — only operators are code.

Supported operators (see docs/RULES.md for full semantics):

    var, and, or, not / !, !!, if / ?:, ==, !=, ===, !==,
    >, >=, <, <=, in, regex, substr, toNumber, missing

Value semantics
---------------
* Missing values (absent field, empty string, null) are ``None``.
* Truthiness follows JSONLogic: ``None``, ``False``, ``0``, ``""`` and ``[]``
  are falsy.
* Ordering comparisons coerce numeric strings to numbers. A comparison with
  a missing operand is *false* (never silently true, unlike JavaScript's
  ``null >= 0``). Comparing a number with a non-numeric string raises
  :class:`EvaluationError`, which the rule runner reports as ``ERROR``.
* ``toNumber`` additionally converts an ISO date ``YYYY-MM-DD`` into the
  integer ``YYYYMMDD`` (documented extension: JSONLogic has no date type,
  and the supplied MiFID-4 rule compares ``toNumber(substr(Timestamp,0,10))``
  with ``"20180101"``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

MAX_DEPTH = 64
MAX_REGEX_LENGTH = 512
_NUMERIC_RE = re.compile(r"^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$")
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class RuleExpressionError(ValueError):
    """The expression itself is invalid (unknown operator, wrong arity, bad regex)."""


class EvaluationError(ValueError):
    """The expression is valid but could not be evaluated against this record."""


# --------------------------------------------------------------------------- helpers


def truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, (str, list, tuple, dict)):
        return len(value) > 0
    return bool(value)


def to_number(value: Any) -> int | float | None:
    """Numeric view of a value, or None when it is not numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and _NUMERIC_RE.match(value):
        number = float(value)
        return int(number) if number.is_integer() and "." not in value and "e" not in value.lower() else number
    return None


def _normalise_missing(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def loose_equals(a: Any, b: Any) -> bool:
    a, b = _normalise_missing(a), _normalise_missing(b)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else False
    na, nb = to_number(a), to_number(b)
    if na is not None and nb is not None and (not isinstance(a, str) or not isinstance(b, str)):
        return na == nb
    return a == b


def compare_ordered(op: str, a: Any, b: Any) -> bool:
    """Ordering comparison. Missing operand -> False. Incomparable types -> EvaluationError."""
    a, b = _normalise_missing(a), _normalise_missing(b)
    if a is None or b is None:
        return False
    na, nb = to_number(a), to_number(b)
    if na is not None and nb is not None:
        left, right = na, nb
    elif isinstance(a, str) and isinstance(b, str):
        left, right = a, b
    else:
        raise EvaluationError(f"cannot compare {a!r} with {b!r} using {op!r}")
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    raise RuleExpressionError(f"unknown comparison {op!r}")


@lru_cache(maxsize=256)
def compile_regex(pattern: str) -> re.Pattern[str]:
    if not isinstance(pattern, str):
        raise RuleExpressionError("regex pattern must be a string")
    if len(pattern) > MAX_REGEX_LENGTH:
        raise RuleExpressionError(f"regex pattern longer than {MAX_REGEX_LENGTH} characters")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise RuleExpressionError(f"invalid regex {pattern!r}: {exc}") from exc


def resolve_var(data: dict[str, Any], path: Any, default: Any = None) -> Any:
    if path is None or path == "":
        return data
    if isinstance(path, (int, float)) and not isinstance(path, bool):
        path = str(int(path))
    if not isinstance(path, str):
        raise RuleExpressionError(f"var path must be a string, got {path!r}")
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    current = _normalise_missing(current)
    return default if current is None else current


def iso_date_to_number(value: str) -> int | None:
    m = _ISO_DATE_RE.match(value.strip())
    if not m:
        return None
    year, month, day = (int(g) for g in m.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return year * 10000 + month * 100 + day


# --------------------------------------------------------------------------- operator registry


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    min_args: int
    max_args: int | None
    lazy: bool = False
    func: Callable[..., Any] | None = None
    description: str = ""


def _op_substr(source: Any, start: Any = 0, length: Any = None) -> Any:
    if source is None:
        return None
    text = str(source)
    s = to_number(start)
    if s is None:
        raise EvaluationError(f"substr start must be numeric, got {start!r}")
    s = int(s)
    result = text[s:] if s >= 0 else text[len(text) + s :]
    if length is not None:
        n = to_number(length)
        if n is None:
            raise EvaluationError(f"substr length must be numeric, got {length!r}")
        n = int(n)
        result = result[:n] if n >= 0 else result[: len(result) + n]
    return result


def _op_to_number(value: Any) -> Any:
    value = _normalise_missing(value)
    if value is None:
        return None
    number = to_number(value)
    if number is not None:
        return number
    if isinstance(value, str):
        as_date = iso_date_to_number(value)
        if as_date is not None:
            return as_date
    raise EvaluationError(f"toNumber cannot convert {value!r} to a number")


def _op_in(needle: Any, haystack: Any) -> bool:
    needle = _normalise_missing(needle)
    if needle is None or haystack is None:
        return False
    if isinstance(haystack, (list, tuple)):
        return any(loose_equals(needle, item) for item in haystack)
    if isinstance(haystack, str):
        return str(needle) in haystack
    raise EvaluationError(f"'in' expects a list or string, got {type(haystack).__name__}")


def _op_regex(value: Any, pattern: Any) -> bool:
    value = _normalise_missing(value)
    if value is None:
        return False
    return compile_regex(pattern).search(str(value)) is not None


def _op_ordered(op: str) -> Callable[..., bool]:
    def run(*args: Any) -> bool:
        if len(args) == 3 and op in {"<", "<="}:
            return compare_ordered(op, args[0], args[1]) and compare_ordered(op, args[1], args[2])
        return compare_ordered(op, args[0], args[1])

    return run


def _op_strict_eq(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


OPERATORS: dict[str, OperatorSpec] = {
    "var": OperatorSpec("var", 0, 2, description="Read a field from the record (dotted paths allowed)"),
    "and": OperatorSpec("and", 1, None, lazy=True, description="All operands truthy (short-circuit)"),
    "or": OperatorSpec("or", 1, None, lazy=True, description="Any operand truthy (short-circuit)"),
    "if": OperatorSpec("if", 1, None, lazy=True, description="if/then/elseif/else chain"),
    "?:": OperatorSpec("?:", 3, 3, lazy=True, description="Ternary"),
    "not": OperatorSpec("not", 1, 1, func=lambda v: not truthy(v), description="Logical negation"),
    "!": OperatorSpec("!", 1, 1, func=lambda v: not truthy(v), description="Logical negation"),
    "!!": OperatorSpec("!!", 1, 1, func=truthy, description="Cast to boolean"),
    "==": OperatorSpec("==", 2, 2, func=loose_equals, description="Loose equality (numeric strings compare as numbers)"),
    "!=": OperatorSpec("!=", 2, 2, func=lambda a, b: not loose_equals(a, b), description="Loose inequality"),
    "===": OperatorSpec("===", 2, 2, func=_op_strict_eq, description="Strict equality"),
    "!==": OperatorSpec("!==", 2, 2, func=lambda a, b: not _op_strict_eq(a, b), description="Strict inequality"),
    ">": OperatorSpec(">", 2, 2, func=_op_ordered(">"), description="Greater than"),
    ">=": OperatorSpec(">=", 2, 2, func=_op_ordered(">="), description="Greater than or equal"),
    "<": OperatorSpec("<", 2, 3, func=_op_ordered("<"), description="Less than (3 args: between, exclusive)"),
    "<=": OperatorSpec("<=", 2, 3, func=_op_ordered("<="), description="Less or equal (3 args: between, inclusive)"),
    "in": OperatorSpec("in", 2, 2, func=_op_in, description="Membership in a list, or substring of a string"),
    "regex": OperatorSpec("regex", 2, 2, func=_op_regex, description="Value matches regular expression (re.search)"),
    "substr": OperatorSpec("substr", 2, 3, func=_op_substr, description="Substring with JSONLogic semantics"),
    "toNumber": OperatorSpec("toNumber", 1, 1, func=_op_to_number, description="Number conversion (ISO date -> YYYYMMDD)"),
    "missing": OperatorSpec("missing", 1, None, description="List of field names that are missing"),
}


# --------------------------------------------------------------------------- structure


def operator_of(expr: Any) -> tuple[str, list[Any]] | None:
    """Return (operator, args) for an operation node, or None for a literal."""
    if isinstance(expr, dict):
        if len(expr) != 1:
            raise RuleExpressionError(f"operation objects must have exactly one key, got {list(expr)}")
        op, args = next(iter(expr.items()))
        if not isinstance(args, list):
            args = [args]
        return op, args
    return None


def validate_expression(expr: Any, depth: int = 0, path: str = "$") -> list[str]:
    """Static validation: operators exist, arity is right, regexes compile."""
    errors: list[str] = []
    if depth > MAX_DEPTH:
        return [f"{path}: expression nested deeper than {MAX_DEPTH} levels"]
    if isinstance(expr, list):
        for i, item in enumerate(expr):
            errors.extend(validate_expression(item, depth + 1, f"{path}[{i}]"))
        return errors
    try:
        node = operator_of(expr)
    except RuleExpressionError as exc:
        return [f"{path}: {exc}"]
    if node is None:
        return errors
    op, args = node
    spec = OPERATORS.get(op)
    if spec is None:
        return [f"{path}: unsupported operator {op!r}"]
    if len(args) < spec.min_args or (spec.max_args is not None and len(args) > spec.max_args):
        expected = f"{spec.min_args}" if spec.min_args == spec.max_args else f"{spec.min_args}..{spec.max_args or 'n'}"
        errors.append(f"{path}: operator {op!r} expects {expected} argument(s), got {len(args)}")
    if op == "var" and args and not isinstance(args[0], (str, int)):
        errors.append(f"{path}: var path must be a string")
    if op == "regex" and len(args) >= 2:
        if isinstance(args[1], str):
            try:
                compile_regex(args[1])
            except RuleExpressionError as exc:
                errors.append(f"{path}: {exc}")
        else:
            errors.append(f"{path}: regex pattern must be a string literal")
    if op == "if" and len(args) >= 2 and len(args) % 2 == 0:
        # if with an even number of args has no else branch: allowed (else -> null), but flag it.
        pass
    for i, arg in enumerate(args):
        errors.extend(validate_expression(arg, depth + 1, f"{path}.{op}[{i}]"))
    return errors


def fields_in(expr: Any) -> list[str]:
    """All var paths referenced by an expression, in first-seen order."""
    found: list[str] = []

    def walk(e: Any) -> None:
        if isinstance(e, list):
            for item in e:
                walk(item)
            return
        node = operator_of(e) if isinstance(e, dict) else None
        if node is None:
            return
        op, args = node
        if op == "var" and args and isinstance(args[0], str):
            if args[0] not in found:
                found.append(args[0])
            return
        if op == "missing":
            for a in args:
                if isinstance(a, str) and a not in found:
                    found.append(a)
        for a in args:
            walk(a)

    walk(expr)
    return found


# --------------------------------------------------------------------------- evaluation


@dataclass
class EvalStats:
    nodes: int = 0
    used_date_conversion: bool = False
    notes: list[str] = field(default_factory=list)


def evaluate(expr: Any, data: dict[str, Any], depth: int = 0, stats: EvalStats | None = None) -> Any:
    if depth > MAX_DEPTH:
        raise RuleExpressionError(f"expression nested deeper than {MAX_DEPTH} levels")
    if stats is not None:
        stats.nodes += 1
    if isinstance(expr, list):
        return [evaluate(item, data, depth + 1, stats) for item in expr]
    node = operator_of(expr)
    if node is None:
        return expr
    op, args = node
    spec = OPERATORS.get(op)
    if spec is None:
        raise RuleExpressionError(f"unsupported operator {op!r}")
    if len(args) < spec.min_args or (spec.max_args is not None and len(args) > spec.max_args):
        raise RuleExpressionError(f"operator {op!r} called with {len(args)} argument(s)")

    if op == "var":
        path = evaluate(args[0], data, depth + 1, stats) if args else None
        default = evaluate(args[1], data, depth + 1, stats) if len(args) > 1 else None
        return resolve_var(data, path, default)
    if op == "missing":
        names = []
        for a in args:
            value = evaluate(a, data, depth + 1, stats)
            names.extend(value if isinstance(value, list) else [value])
        return [n for n in names if resolve_var(data, n) is None]
    if op == "and":
        value: Any = True
        for a in args:
            value = evaluate(a, data, depth + 1, stats)
            if not truthy(value):
                return value
        return value
    if op == "or":
        value = False
        for a in args:
            value = evaluate(a, data, depth + 1, stats)
            if truthy(value):
                return value
        return value
    if op in {"if", "?:"}:
        i = 0
        while i + 1 < len(args):
            if truthy(evaluate(args[i], data, depth + 1, stats)):
                return evaluate(args[i + 1], data, depth + 1, stats)
            i += 2
        return evaluate(args[i], data, depth + 1, stats) if i < len(args) else None

    values = [evaluate(a, data, depth + 1, stats) for a in args]
    if op == "toNumber" and stats is not None and isinstance(values[0], str) and iso_date_to_number(values[0]):
        stats.used_date_conversion = True
    assert spec.func is not None
    return spec.func(*values)


def selected_if_branch(expr: Any, data: dict[str, Any]) -> tuple[int | None, Any]:
    """For a top-level ``if``: index of the selected branch argument and the branch expression.

    Returns (None, None) when ``expr`` is not an ``if``.
    """
    node = operator_of(expr) if isinstance(expr, dict) else None
    if node is None or node[0] not in {"if", "?:"}:
        return None, None
    _, args = node
    i = 0
    while i + 1 < len(args):
        if truthy(evaluate(args[i], data)):
            return i + 1, args[i + 1]
        i += 2
    if i < len(args):
        return i, args[i]
    return None, None
