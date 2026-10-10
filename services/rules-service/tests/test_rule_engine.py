"""Rule loading, normalisation and PASS / FAIL / NOT_APPLICABLE / ERROR on the supplied rules."""

from __future__ import annotations

import json

from app.engine import ERROR, FAIL, NOT_APPLICABLE, PASS, Overlay, build_rule_set, evaluate_rule
from app.engine.normalization import normalize_logic, normalize_schema

FIELDS = {"Trade_ID", "Asset_Class", "Timestamp", "Counterparty_LEI", "Price", "Quantity", "Currency", "Maturity_Date", "Underlying_ISIN"}
GOOD_TRADE = {
    "Trade_ID": "T1",
    "Asset_Class": "Derivative",
    "Timestamp": "2024-06-25T09:15:00Z",
    "Counterparty_LEI": "5493001KJTI42S8N5L34",
    "Price": 10.0,
    "Quantity": 5,
    "Currency": "EUR",
    "Maturity_Date": "2025-12-31",
    "Underlying_ISIN": "US0378331005",
}


def test_supplied_rules_load_valid_with_documented_normalisation(rules) -> None:  # type: ignore[no-untyped-def]
    assert set(rules) == {"MIFID-1", "MIFID-2", "MIFID-3", "MIFID-4", "EMIR-1", "EMIR-2", "FCA-1", "FCA-2"}
    assert all(r.valid for r in rules.values())
    mifid1 = rules["MIFID-1"]
    assert mifid1.source_logic["and"][1]["regex"][0] == "Counterparty_LEI"  # original preserved
    assert mifid1.logic["and"][1]["regex"][0] == {"var": "Counterparty_LEI"}
    assert mifid1.logic["and"][1]["regex"][1] == "^[0-9A-Z]{20}$"
    assert any(n.startswith("regex_anchor_dedup") for n in mifid1.notes)
    assert rules["EMIR-1"].applies_when_source == "overlay"
    assert any(n.startswith("toNumber") for n in rules["MIFID-4"].notes)


def test_pass(rules) -> None:  # type: ignore[no-untyped-def]
    for rule_id in ("MIFID-1", "MIFID-2", "MIFID-3", "MIFID-4", "EMIR-1", "EMIR-2", "FCA-1", "FCA-2"):
        assert evaluate_rule(rules[rule_id], GOOD_TRADE).status == PASS, rule_id


def test_fail_with_field_level_explanation(rules) -> None:  # type: ignore[no-untyped-def]
    res = evaluate_rule(rules["MIFID-2"], {**GOOD_TRADE, "Price": -99.9})
    assert res.status == FAIL
    assert res.affected_fields == ["Price"]
    assert res.category == "negative_value"
    assert "Price is -99.9" in res.explanation and "cannot be negative" in res.explanation
    res = evaluate_rule(rules["MIFID-1"], {**GOOD_TRADE, "Counterparty_LEI": "12345"})
    assert res.category == "invalid_format" and "'12345'" in res.explanation
    res = evaluate_rule(rules["MIFID-4"], {**GOOD_TRADE, "Timestamp": "2017-12-31T23:59:59Z"})
    assert res.status == FAIL and res.category == "date_constraint"


def test_conditional_rule_not_applicable_for_other_asset_classes(rules) -> None:  # type: ignore[no-untyped-def]
    equity = {**GOOD_TRADE, "Asset_Class": "Equity", "Maturity_Date": None, "Underlying_ISIN": None}
    assert evaluate_rule(rules["MIFID-3"], equity).status == NOT_APPLICABLE
    assert evaluate_rule(rules["EMIR-1"], equity).status == NOT_APPLICABLE  # not penalised
    derivative_missing = {**GOOD_TRADE, "Maturity_Date": None, "Underlying_ISIN": None}
    r3 = evaluate_rule(rules["MIFID-3"], derivative_missing)
    assert r3.status == FAIL and r3.conditional and r3.affected_fields == ["Maturity_Date"]
    e1 = evaluate_rule(rules["EMIR-1"], derivative_missing)
    assert e1.status == FAIL and e1.affected_fields == ["Underlying_ISIN"]
    assert evaluate_rule(rules["FCA-2"], {**GOOD_TRADE, "Asset_Class": "FX", "Counterparty_LEI": None}).status == NOT_APPLICABLE


def test_invalid_rule_configuration_reports_error_never_pass() -> None:
    obj = {"regulator": "X", "rules": [{"id": "X-1", "description": "bad", "logic": {"lookup": [{"var": "Price"}]}}]}
    rs = build_rule_set(obj, "x.json", json.dumps(obj).encode(), FIELDS, Overlay())
    rule = rs.rules[0]
    assert not rule.valid and "unsupported operator 'lookup'" in rule.errors[0]
    assert evaluate_rule(rule, GOOD_TRADE).status == ERROR


def test_runtime_type_error_is_error_status(rules) -> None:  # type: ignore[no-untyped-def]
    res = evaluate_rule(rules["MIFID-2"], {**GOOD_TRADE, "Price": "N/A"})
    assert res.status == ERROR and "cannot compare" in res.explanation


def test_zero_code_rule_addition() -> None:
    obj = {
        "regulator": "Demo",
        "rules": [
            {
                "id": "DEMO-1",
                "description": "Maturity after trade date",
                "applies_when": {"==": [{"var": "Asset_Class"}, "Derivative"]},
                "logic": {">": [{"var": "Maturity_Date"}, {"substr": [{"var": "Timestamp"}, 0, 10]}]},
                "severity": "high",
                "unknown_field_check": True,
            }
        ],
    }
    rule = build_rule_set(obj, "demo.json", b"{}", FIELDS, Overlay()).rules[0]
    assert rule.valid and rule.severity == "high"
    assert evaluate_rule(rule, GOOD_TRADE).status == PASS
    assert evaluate_rule(rule, {**GOOD_TRADE, "Maturity_Date": "2020-01-01"}).status == FAIL
    assert evaluate_rule(rule, {**GOOD_TRADE, "Asset_Class": "Bond"}).status == NOT_APPLICABLE


def test_field_alias_and_unknown_field_warning() -> None:
    logic, notes = normalize_logic({">=": [{"var": "Execution_Timestamp"}, "2018"]}, FIELDS, {"Execution_Timestamp": "Timestamp"})
    assert logic == {">=": [{"var": "Timestamp"}, "2018"]}
    assert notes and notes[0].startswith("field_alias")
    obj = {"regulator": "X", "rules": [{"id": "X-2", "description": "d", "logic": {"var": "Notional_Amount"}}]}
    rule = build_rule_set(obj, "x.json", b"{}", FIELDS, Overlay()).rules[0]
    assert any("Notional_Amount" in w for w in rule.warnings)


def test_schema_normalisation() -> None:
    schema, notes = normalize_schema({"$$schema": "x", "properties": {"L": {"pattern": "^[A-Z]{2}$$"}, "E": {"pattern": "^a\\$$"}}})
    assert schema["$schema"] == "x" and "$$schema" not in schema
    assert schema["properties"]["L"]["pattern"] == "^[A-Z]{2}$"
    assert schema["properties"]["E"]["pattern"] == "^a\\$$"  # escaped literal $ kept
    assert len(notes) == 2
