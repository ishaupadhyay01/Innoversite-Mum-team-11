"""A small, dependency-free JSONLogic evaluator (https://jsonlogic.com) with:

* every standard operator (var, missing, missing_some, if/?:, ==, ===, !=, !==, !, !!, or, and,
  <, <=, >, >=, between, +, -, *, /, %, min, max, cat, substr, in, merge, map, filter, reduce,
  all, some, none, log);
* a registry for custom operators (see ``operations.py``) so new rule *primitives* can be added
  without touching the evaluator, while rules themselves stay pure JSON (no code changes);
* **strict-null comparisons** (deliberate deviation from JS): ``null >= 0`` is *false*. In compliance
  checks a missing value must never satisfy a numeric threshold.

Why not a PyPI package? The maintained options lack custom-operator hooks and lazy evaluation, both
needed for the dataset's ``regex``/``toNumber`` operators and for generating explanations.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

Data = dict[str, Any]
# (engine, raw_args, data) -> value. Lazy operators receive *unevaluated* args.
OpFn = Callable[["JsonLogic", list[Any], Data], Any]


class JsonLogicError(ValueError):
    pass


class UnknownOperatorError(JsonLogicError):
    pass


def truthy(value: Any) -> bool:
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, (list, tuple, str, dict)):
        return len(value) > 0
    return bool(value)


def to_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip()
        try:
            f = float(s)
        except ValueError:
            return None
        return int(f) if f.is_integer() and "." not in s and "e" not in s.lower() else f
    return None


def _coerce_pair(a: Any, b: Any) -> tuple[Any, Any] | None:
    """Return comparable values or None when the comparison is undefined (strict null)."""
    if a is None or b is None:
        return None
    if isinstance(a, str) and isinstance(b, str):
        return a, b
    na, nb = to_number(a), to_number(b)
    if na is None or nb is None:
        return None
    return na, nb


def loose_equals(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if type(a) is type(b) or (isinstance(a, str) and isinstance(b, str)):
        return a == b
    pair = _coerce_pair(a, b)
    return pair is not None and pair[0] == pair[1]


class JsonLogic:
    def __init__(self) -> None:
        self._ops: dict[str, tuple[OpFn, bool]] = {}
        _register_standard(self)

    # -- registry ---------------------------------------------------------------------------
    def register(self, name: str, fn: OpFn, *, lazy: bool = False) -> None:
        self._ops[name] = (fn, lazy)

    def operation(self, name: str, *, lazy: bool = False) -> Callable[[OpFn], OpFn]:
        def deco(fn: OpFn) -> OpFn:
            self.register(name, fn, lazy=lazy)
            return fn

        return deco

    @property
    def operators(self) -> set[str]:
        return set(self._ops)

    # -- evaluation -------------------------------------------------------------------------
    @staticmethod
    def is_logic(obj: Any) -> bool:
        return isinstance(obj, dict) and len(obj) == 1

    def apply(self, logic: Any, data: Data | None = None) -> Any:
        data = data or {}
        if isinstance(logic, list):
            return [self.apply(item, data) for item in logic]
        if not self.is_logic(logic):
            return logic
        op, args = next(iter(logic.items()))
        if op not in self._ops:
            raise UnknownOperatorError(f"Unknown operator '{op}'")
        fn, lazy = self._ops[op]
        if not isinstance(args, list):
            args = [args]
        if not lazy:
            args = [self.apply(a, data) for a in args]
        return fn(self, args, data)

    def referenced_vars(self, logic: Any) -> list[str]:
        found: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, list):
                for n in node:
                    walk(n)
            elif self.is_logic(node):
                op, args = next(iter(node.items()))
                if op == "var":
                    name = args[0] if isinstance(args, list) and args else args
                    if isinstance(name, str) and name and name not in found:
                        found.append(name)
                else:
                    walk(args)

        walk(logic)
        return found

    def unknown_operators(self, logic: Any) -> set[str]:
        bad: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, list):
                for n in node:
                    walk(n)
            elif self.is_logic(node):
                op, args = next(iter(node.items()))
                if op not in self._ops:
                    bad.add(op)
                walk(args)

        walk(logic)
        return bad


def get_var(data: Any, path: Any, default: Any = None) -> Any:
    if path in (None, "", []):
        return data
    if isinstance(path, (int, float)):
        path = str(int(path))
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return default if current is None else current


def _register_standard(e: JsonLogic) -> None:
    r = e.register

    def var(_: JsonLogic, a: list[Any], d: Data) -> Any:
        return get_var(d, a[0] if a else None, a[1] if len(a) > 1 else None)

    def missing(_: JsonLogic, a: list[Any], d: Data) -> list[str]:
        keys = a[0] if len(a) == 1 and isinstance(a[0], list) else a
        return [k for k in keys if get_var(d, k) in (None, "")]

    def missing_some(eng: JsonLogic, a: list[Any], d: Data) -> list[str]:
        need, keys = a[0], a[1]
        miss = missing(eng, [keys], d)
        return [] if len(keys) - len(miss) >= need else miss

    def if_(eng: JsonLogic, a: list[Any], d: Data) -> Any:
        i = 0
        while i < len(a) - 1:
            if truthy(eng.apply(a[i], d)):
                return eng.apply(a[i + 1], d)
            i += 2
        return eng.apply(a[i], d) if i < len(a) else None

    def and_(eng: JsonLogic, a: list[Any], d: Data) -> Any:
        value: Any = True
        for item in a:
            value = eng.apply(item, d)
            if not truthy(value):
                return value
        return value

    def or_(eng: JsonLogic, a: list[Any], d: Data) -> Any:
        value: Any = False
        for item in a:
            value = eng.apply(item, d)
            if truthy(value):
                return value
        return value

    def cmp(fn: Callable[[Any, Any], bool]) -> OpFn:
        def inner(_: JsonLogic, a: list[Any], __: Data) -> bool:
            pairs = list(zip(a, a[1:], strict=False))  # supports between: {"<": [1, x, 10]}
            for x, y in pairs:
                c = _coerce_pair(x, y)
                if c is None or not fn(*c):
                    return False
            return True

        return inner

    def nums(a: list[Any]) -> list[float | int]:
        out = [to_number(x) for x in a]
        if any(x is None for x in out):
            raise JsonLogicError(f"Non-numeric argument in {a!r}")
        return out  # type: ignore[return-value]

    def substr(_: JsonLogic, a: list[Any], __: Data) -> str:
        s = "" if a[0] is None else str(a[0])
        start = int(a[1]) if len(a) > 1 else 0
        if len(a) > 2:
            length = int(a[2])
            end = len(s) + length if length < 0 else start + length if start >= 0 else len(s) + start + length
            return s[start:end]
        return s[start:]

    def in_(_: JsonLogic, a: list[Any], __: Data) -> bool:
        needle, hay = a[0], a[1]
        if hay is None or needle is None:
            return False
        return needle in hay if isinstance(hay, (list, str)) else False

    def merge(_: JsonLogic, a: list[Any], __: Data) -> list[Any]:
        out: list[Any] = []
        for x in a:
            out.extend(x if isinstance(x, list) else [x])
        return out

    def map_(eng: JsonLogic, a: list[Any], d: Data) -> list[Any]:
        items = eng.apply(a[0], d) or []
        return [eng.apply(a[1], item) for item in items]

    def filter_(eng: JsonLogic, a: list[Any], d: Data) -> list[Any]:
        items = eng.apply(a[0], d) or []
        return [item for item in items if truthy(eng.apply(a[1], item))]

    def reduce_(eng: JsonLogic, a: list[Any], d: Data) -> Any:
        items = eng.apply(a[0], d) or []
        acc = eng.apply(a[2], d) if len(a) > 2 else None
        for item in items:
            acc = eng.apply(a[1], {"current": item, "accumulator": acc})
        return acc

    def all_(eng: JsonLogic, a: list[Any], d: Data) -> bool:
        items = eng.apply(a[0], d) or []
        return bool(items) and all(truthy(eng.apply(a[1], i)) for i in items)

    def some_(eng: JsonLogic, a: list[Any], d: Data) -> bool:
        return any(truthy(eng.apply(a[1], i)) for i in (eng.apply(a[0], d) or []))

    def none_(eng: JsonLogic, a: list[Any], d: Data) -> bool:
        return not some_(eng, a, d)

    def minus(_: JsonLogic, a: list[Any], __: Data) -> float | int:
        n = nums(a)
        return -n[0] if len(n) == 1 else n[0] - n[1]

    def div(_: JsonLogic, a: list[Any], __: Data) -> float:
        n = nums(a)
        if n[1] == 0:
            raise JsonLogicError("Division by zero")
        return n[0] / n[1]

    r("var", var)
    r("missing", missing)
    r("missing_some", missing_some)
    r("if", if_, lazy=True)
    r("?:", if_, lazy=True)
    r("and", and_, lazy=True)
    r("or", or_, lazy=True)
    r("==", lambda _, a, __: loose_equals(a[0], a[1]))
    r("===", lambda _, a, __: type(a[0]) is type(a[1]) and a[0] == a[1])
    r("!=", lambda _, a, __: not loose_equals(a[0], a[1]))
    r("!==", lambda _, a, __: not (type(a[0]) is type(a[1]) and a[0] == a[1]))
    r("!", lambda _, a, __: not truthy(a[0] if a else None))
    r("!!", lambda _, a, __: truthy(a[0] if a else None))
    r("<", cmp(lambda x, y: x < y))
    r("<=", cmp(lambda x, y: x <= y))
    r(">", cmp(lambda x, y: x > y))
    r(">=", cmp(lambda x, y: x >= y))
    r("+", lambda _, a, __: sum(nums(a)))
    r("-", minus)
    r("*", lambda _, a, __: math.prod(nums(a)))
    r("/", div)
    r("%", lambda _, a, __: nums(a)[0] % nums(a)[1])
    r("min", lambda _, a, __: min(nums(a)) if a else None)
    r("max", lambda _, a, __: max(nums(a)) if a else None)
    r("cat", lambda _, a, __: "".join("" if x is None else str(x) for x in a))
    r("substr", substr)
    r("in", in_)
    r("merge", merge)
    r("map", map_, lazy=True)
    r("filter", filter_, lazy=True)
    r("reduce", reduce_, lazy=True)
    r("all", all_, lazy=True)
    r("some", some_, lazy=True)
    r("none", none_, lazy=True)
    r("log", lambda _, a, __: a[0] if a else None)
