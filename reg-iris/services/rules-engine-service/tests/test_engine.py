import json

import pytest

from app.engine import RuleFileError, Status, evaluate_rule, load_rule_file
from tests.conftest import DATA, FIELDS


def _rules(name):
    return {r.code: r for r in load_rule_file((DATA / "rules" / name).read_bytes(), FIELDS).rules}


def trade(**kw):
    base = {
        "Trade_ID": "T1",
        "Asset_Class": "Equity",
        "Timestamp": "2024-06-25T09:15:00Z",
        "Counterparty_LEI": "5493001KJTI42S8N5L34",
        "Price": 10.0,
        "Quantity": 5,
        "Currency": "USD",
        "Maturity_Date": None,
        "Underlying_ISIN": None,
    }
    return {**base, **kw}


def test_negative_price_fails_with_explanation_and_citation():
    out = evaluate_rule(_rules("rules_mifid.json")["MIFID-2"], trade(Price=-99.9))
    assert out.status is Status.FAIL
    assert out.explanation.startswith("Price (-99.9) must be ≥ 0 — required by MiFID II rule MIFID-2")
    assert out.field_values == {"Price": -99.9}


def test_missing_lei_is_explained():
    out = evaluate_rule(_rules("rules_mifid.json")["MIFID-1"], trade(Counterparty_LEI=None))
    assert out.status is Status.FAIL and "Counterparty_LEI is required but is missing" in out.explanation


def test_scoped_if_rules_are_not_applicable_outside_scope():
    mifid3 = _rules("rules_mifid.json")["MIFID-3"]
    assert evaluate_rule(mifid3, trade()).status is Status.NOT_APPLICABLE
    assert evaluate_rule(mifid3, trade(Asset_Class="Derivative")).status is Status.FAIL
    assert evaluate_rule(mifid3, trade(Asset_Class="Derivative", Maturity_Date="2027-01-01")).status is Status.PASS
    fca2 = _rules("rules_fca.json")["FCA-2"]
    assert evaluate_rule(fca2, trade(Asset_Class="FX", Counterparty_LEI=None)).status is Status.NOT_APPLICABLE


def test_applies_when_extension():
    raw = {
        "regulator": "EMIR",
        "rules": [
            {
                "id": "EMIR-1b",
                "description": "Derivatives need ISIN",
                "applies_when": {"==": [{"var": "Asset_Class"}, "Derivative"]},
                "logic": {"regex": ["Underlying_ISIN", "^[A-Z0-9]{12}$"]},
            }
        ],
    }
    rule = load_rule_file(json.dumps(raw), FIELDS).rules[0]
    assert evaluate_rule(rule, trade()).status is Status.NOT_APPLICABLE
    assert evaluate_rule(rule, trade(Asset_Class="Derivative")).status is Status.FAIL


def test_linter_flags_emir1_scoping_bug():
    loaded = load_rule_file((DATA / "rules" / "rules_emir.json").read_bytes(), FIELDS)
    assert any(i.rule_code == "EMIR-1" and "scoping condition" in i.message for i in loaded.issues)


@pytest.mark.parametrize(
    "raw,needle",
    [
        ('{"regulator": "X"}', "rules"),
        ('{"regulator": "X", "rules": [{"id": "R1", "description": "d", "logic": {"nope": [1]}}]}', "Unknown operator"),
        ("{not json", "Invalid JSON"),
    ],
)
def test_bad_rule_files_are_rejected(raw, needle):
    with pytest.raises(RuleFileError) as exc:
        load_rule_file(raw, FIELDS)
    assert needle in str(exc.value) + " ".join(i.message for i in exc.value.issues)
