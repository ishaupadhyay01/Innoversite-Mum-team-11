import pytest

from app.engine.jsonlogic import JsonLogic, UnknownOperatorError
from app.engine.operations import ENGINE, isin_checksum_ok, lei_checksum_ok


@pytest.mark.parametrize(
    "logic,data,expected",
    [
        ({"var": "a.b"}, {"a": {"b": 3}}, 3),
        ({"var": ["missing", "dflt"]}, {}, "dflt"),
        ({"missing": ["a", "b"]}, {"a": 1, "b": ""}, ["b"]),
        ({"if": [{"==": [{"var": "x"}, "FX"]}, "fx", "other"]}, {"x": "FX"}, "fx"),
        ({"in": [{"var": "c"}, ["USD", "EUR"]]}, {"c": "XYZ"}, False),
        ({"==": [1, "1"]}, {}, True),
        ({"<": [0, {"var": "q"}, 10]}, {"q": 5}, True),
        ({"substr": ["2024-06-25T09:15:00Z", 0, 10]}, {}, "2024-06-25"),
        ({"cat": ["a", None, 1]}, {}, "a1"),
    ],
)
def test_standard_operators(logic, data, expected):
    assert ENGINE.apply(logic, data) == expected


def test_strict_null_comparisons_never_pass():
    # JS JSONLogic says null >= 0 is true; a missing Price must not satisfy "Price >= 0".
    assert ENGINE.apply({">=": [{"var": "Price"}, 0]}, {"Price": None}) is False


def test_regex_field_name_shorthand_and_todate_number():
    rule = {"regex": ["Counterparty_LEI", "^[0-9A-Z]{20}$$"]}
    assert ENGINE.apply(rule, {"Counterparty_LEI": "5493001KJTI42S8N5L34"}) is True
    assert ENGINE.apply(rule, {"Counterparty_LEI": "BADLEI"}) is False
    assert ENGINE.apply({"toNumber": "2017-12-31T23:59:59Z"}) == 20171231


def test_identifier_checksums():
    assert lei_checksum_ok("HWUPKR0MPOU8FGXBT394") is True  # Apple Inc.
    assert lei_checksum_ok("5493001KJTI42S8N5L34") is False  # format-valid, but fails ISO 17442 check digits
    assert isin_checksum_ok("US0378331005") is True  # Apple Inc.
    assert isin_checksum_ok("US0378331006") is False


def test_unknown_operator_is_rejected():
    with pytest.raises(UnknownOperatorError):
        JsonLogic().apply({"regex": ["a", "b"]}, {})
