"""Generic expression interpreter: operators, missing values, errors (no eval)."""

from __future__ import annotations

import pytest

from app.engine.expressions import EvaluationError, RuleExpressionError, evaluate, truthy, validate_expression


@pytest.mark.parametrize(
    ("expr", "data", "expected"),
    [
        ({"==": [{"var": "A"}, "FX"]}, {"A": "FX"}, True),
        ({"!=": [{"var": "A"}, "FX"]}, {"A": "FX"}, False),
        ({">=": [{"var": "P"}, 0]}, {"P": "0.0"}, True),  # numeric string coerced
        ({">": [{"var": "Q"}, 0]}, {"Q": 0}, False),
        ({"<": [1, {"var": "x"}, 10]}, {"x": 5}, True),  # between
        ({"in": [{"var": "C"}, ["USD", "EUR"]]}, {"C": "XYZ"}, False),
        ({"in": ["LEI", "Counterparty_LEI"]}, {}, True),  # substring
        ({"regex": [{"var": "L"}, "^[0-9A-Z]{20}$"]}, {"L": "5493001KJTI42S8N5L34"}, True),
        ({"substr": ["2024-06-25T09:15:00Z", 0, 10]}, {}, "2024-06-25"),
        ({"substr": ["abcdef", -2]}, {}, "ef"),
        ({"toNumber": "2017-12-31"}, {}, 20171231),  # documented ISO-date extension
        ({"toNumber": "12.5"}, {}, 12.5),
        ({"and": [True, {"var": "x"}]}, {"x": ""}, None),  # empty string is missing -> falsy
        ({"or": [False, {"var": "x"}]}, {"x": "y"}, "y"),
        ({"not": {"var": "x"}}, {}, True),
        ({"if": [{"==": [{"var": "a"}, 1]}, "one", {"==": [{"var": "a"}, 2]}, "two", "other"]}, {"a": 2}, "two"),
        ({"missing": ["a", "b"]}, {"a": 1}, ["b"]),
    ],
)
def test_operators(expr: object, data: dict, expected: object) -> None:
    assert evaluate(expr, data) == expected


def test_missing_operand_in_comparison_is_false_not_true() -> None:
    # JavaScript would treat null >= 0 as true; the engine must not.
    assert evaluate({">=": [{"var": "Price"}, 0]}, {"Price": None}) is False
    assert evaluate({">=": [{"var": "Price"}, 0]}, {}) is False


def test_type_mismatch_raises_evaluation_error() -> None:
    with pytest.raises(EvaluationError):
        evaluate({">=": [{"var": "Price"}, 0]}, {"Price": "abc"})
    with pytest.raises(EvaluationError):
        evaluate({"toNumber": "not a number"}, {})


def test_unknown_operator_and_bad_structure_rejected() -> None:
    with pytest.raises(RuleExpressionError):
        evaluate({"eval": ["__import__('os')"]}, {})
    with pytest.raises(RuleExpressionError):
        evaluate({"==": [1, 1], "!=": [1, 2]}, {})
    errors = validate_expression({"and": [{"regex": [{"var": "x"}, "("]}, {"frobnicate": [1]}, {">": [1]}]})
    assert any("invalid regex" in e for e in errors)
    assert any("unsupported operator 'frobnicate'" in e for e in errors)
    assert any("expects 2 argument(s), got 1" in e for e in errors)


def test_truthiness_follows_jsonlogic() -> None:
    assert [truthy(v) for v in (None, False, 0, 0.0, "", [], "0", 1, [0])] == [False] * 6 + [True] * 3
