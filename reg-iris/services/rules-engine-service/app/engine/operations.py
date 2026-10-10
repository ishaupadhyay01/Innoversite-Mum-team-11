"""Custom operators — the "vocabulary" available to JSON rules.

Adding a primitive here (reviewed code) lets compliance users write unlimited new rules in JSON
without further code changes. Every operator must be pure and side-effect free.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from .jsonlogic import Data, JsonLogic, get_var, to_number

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def resolve_field_or_value(engine: JsonLogic, arg: Any, data: Data) -> Any:
    """Dataset convention: ``{"regex": ["Counterparty_LEI", "^...$"]}`` names the *field* as a bare string.
    A bare string equal to a field name is treated as a field reference; logic objects are evaluated."""
    if isinstance(arg, str) and arg in data:
        return get_var(data, arg)
    return engine.apply(arg, data)


def lei_checksum_ok(lei: str) -> bool:
    """ISO 17442: 20 chars, last two are ISO 7064 MOD 97-10 check digits."""
    if not re.fullmatch(r"[0-9A-Z]{18}[0-9]{2}", lei or ""):
        return False
    digits = "".join(str(int(ch, 36)) for ch in lei)
    return int(digits) % 97 == 1


def isin_checksum_ok(isin: str) -> bool:
    """ISO 6166: 2-letter country + 9 alnum + Luhn check digit."""
    if not re.fullmatch(r"[A-Z]{2}[0-9A-Z]{9}[0-9]", isin or ""):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n - 9 if n > 9 else n
    return (10 - total % 10) % 10 == int(isin[-1])


def register_custom_operations(engine: JsonLogic) -> None:
    def regex(eng: JsonLogic, a: list[Any], d: Data) -> bool:
        value = resolve_field_or_value(eng, a[0], d)
        pattern = eng.apply(a[1], d)
        if value in (None, ""):
            return False
        return _compiled(str(pattern)).search(str(value)) is not None

    def to_number_op(_: JsonLogic, a: list[Any], __: Data) -> float | int | None:
        """Numbers and numeric strings → number. ISO dates ('2024-06-25…') → 20240625 so dates compare
        numerically (used by MIFID-4: toNumber(substr(Timestamp, 0, 10)) >= 20180101)."""
        value = a[0] if a else None
        if isinstance(value, str) and (m := _ISO_DATE.match(value.strip())):
            return int("".join(m.groups()))
        return to_number(value)

    def is_date(_: JsonLogic, a: list[Any], __: Data) -> bool:
        value = a[0] if a else None
        if not isinstance(value, str) or not value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def date_diff_days(_: JsonLogic, a: list[Any], __: Data) -> int | None:
        try:
            d1 = date.fromisoformat(str(a[0])[:10])
            d2 = date.fromisoformat(str(a[1])[:10])
        except (ValueError, TypeError, IndexError):
            return None
        return (d1 - d2).days

    engine.register("regex", regex, lazy=True)
    engine.register("toNumber", to_number_op)
    engine.register("isDate", is_date)
    engine.register("dateDiffDays", date_diff_days)
    engine.register("length", lambda _, a, __: len(a[0]) if a and a[0] is not None else 0)
    engine.register("isValidLEI", lambda _, a, __: lei_checksum_ok(str(a[0] or "")))
    engine.register("isValidISIN", lambda _, a, __: isin_checksum_ok(str(a[0] or "")))
    engine.register("lower", lambda _, a, __: str(a[0]).lower() if a and a[0] is not None else None)
    engine.register("upper", lambda _, a, __: str(a[0]).upper() if a and a[0] is not None else None)


def build_engine() -> JsonLogic:
    engine = JsonLogic()
    register_custom_operations(engine)
    return engine


ENGINE = build_engine()
