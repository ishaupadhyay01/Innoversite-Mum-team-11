"""Dataset loading, Impact Matrix, gap analysis, checklist, CSV export and trade questions."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.analysis.core import checklist, combine_and, combined_summary, evaluate_matrix, gap_analysis, select_rules, summarize
from app.analysis.export import MATRIX_COLUMNS, VERDICT_COLUMNS, iter_matrix_csv, safe_cell, summary_csv, verdict_csv
from app.analysis.trade_query import parse_trade_query, run_trade_query
from app.engine.dataset import DatasetError, load_trades, validate_against_schema


def test_csv_ingestion_coerces_types_from_schema(dataset) -> None:  # type: ignore[no-untyped-def]
    assert dataset.count == 200
    assert dataset.columns == [
        "Trade_ID",
        "Asset_Class",
        "Timestamp",
        "Counterparty_LEI",
        "Price",
        "Quantity",
        "Currency",
        "Maturity_Date",
        "Underlying_ISIN",
    ]
    t4 = dataset.by_id()["T000004"]
    assert t4["Price"] == -99.9 and isinstance(t4["Quantity"], int)
    t1 = dataset.by_id()["T000001"]
    assert t1["Maturity_Date"] is None and t1["Underlying_ISIN"] is None  # empty -> missing
    assert dataset.warnings == []


def test_bad_csv_values_are_reported(tmp_path: Path, schema) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "t.csv"
    f.write_text("Trade_ID,Asset_Class,Timestamp,Counterparty_LEI,Price,Quantity,Currency\nT1,FX,2024-01-01T00:00:00Z,X,abc,1.5,USD\n")
    ds = load_trades(f, schema)
    assert any("Price expected a number" in w for w in ds.warnings)
    assert any("Quantity expected an integer" in w for w in ds.warnings)
    with pytest.raises(DatasetError):
        load_trades(tmp_path / "missing.csv", schema)


def test_impact_matrix_on_supplied_data_is_deterministic(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    rule_list = list(rules.values())
    rows = evaluate_matrix(dataset, rule_list)
    assert len(rows) == 200 * 8
    s = summarize(rows, dataset, rule_list)
    assert s["status_counts"] == {"PASS": 1021, "FAIL": 209, "NOT_APPLICABLE": 370, "ERROR": 0}
    assert s["unique_impacted_trades"] == 156
    by_rule = {r["rule_id"]: r for r in s["by_rule"]}
    assert by_rule["MIFID-2"]["fail"] == 8  # negative prices
    assert by_rule["EMIR-2"]["fail"] == 8  # zero quantities
    assert by_rule["FCA-1"]["fail"] == 9  # XYZ currency
    assert by_rule["MIFID-1"]["fail"] == 37  # missing / malformed LEIs
    assert by_rule["MIFID-4"]["fail"] == 1  # 2017 trade
    assert by_rule["EMIR-1"]["not_applicable"] == 165  # only derivatives are in scope
    assert rows == evaluate_matrix(dataset, rule_list)  # same input, same output
    t4 = next(r for r in rows if r["trade_id"] == "T000004" and r["rule_id"] == "MIFID-2")
    assert t4["status"] == "FAIL" and t4["actual_values"] == {"Price": -99.9}
    assert t4["rule_source"] == "rules_mifid.json#MIFID-2"


def test_rule_selection_by_regulator(rules) -> None:  # type: ignore[no-untyped-def]
    assert [r.id for r in select_rules(list(rules.values()), ["fca"])] == ["FCA-1", "FCA-2"]
    assert [r.id for r in select_rules(list(rules.values()), rule_ids=["mifid-2"])] == ["MIFID-2"]


def test_gap_analysis_separates_rule_and_schema_findings(dataset, rules, schema) -> None:  # type: ignore[no-untyped-def]
    rows = evaluate_matrix(dataset, list(rules.values()))
    g = gap_analysis(rows, validate_against_schema(dataset, schema))
    cats = {c["category"]: c for c in g["rule_findings"]["by_category"]}
    assert cats["negative_value"]["failed_evaluations"] == 8
    assert cats["value_not_allowed"]["fields"] == ["Currency"]
    assert g["rule_findings"]["conditional_requirements"]["rule_ids"] == ["FCA-2", "MIFID-3"]
    schema_checks = {(b["field"], b["check"]): b["count"] for b in g["schema_findings"]["by_check"]}
    assert schema_checks[("Counterparty_LEI", "required")] == 18
    assert schema_checks[("Currency", "enum")] == 9


def test_checklist_dataset_and_single_trade(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    rule_list = list(rules.values())
    rows = evaluate_matrix(dataset, rule_list)
    agg = checklist(rows, rule_list)
    mifid3 = next(i for i in agg["items"] if i["rule_id"] == "MIFID-3")
    assert mifid3["applicability"].startswith("Conditional")
    assert mifid3["applicable"] == 35 and mifid3["fail"] == 9
    one = checklist(rows, rule_list, "T000004")
    statuses = {i["rule_id"]: i["status"] for i in one["items"]}
    assert statuses["MIFID-2"] == "FAIL" and statuses["MIFID-3"] == "NOT_APPLICABLE"


def test_csv_export_columns_and_formula_injection_guard(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    rows = [r for r in evaluate_matrix(dataset, list(rules.values())) if r["status"] == "FAIL"][:5]
    rows[0] = {**rows[0], "explanation": '=HYPERLINK("http://evil")'}
    text = "".join(iter_matrix_csv(rows))
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == MATRIX_COLUMNS
    assert len(parsed) == 6
    assert parsed[1][9].startswith("'=HYPERLINK")
    assert safe_cell("-99.9") == "-99.9"  # numbers are data, not formulas
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("+cmd") == "'+cmd"


@pytest.mark.parametrize(
    ("question", "count"),
    [
        ("Which trades are missing a Counterparty LEI?", 18),
        ("Show me all Derivative trades that do not have a Maturity Date.", 9),
        ("List any trade where the price is negative.", 8),
        ("How many trades use a currency that is not in the approved list (USD, EUR, GBP, JPY, CHF)?", 9),
        ("Which trades were executed before 2018‑01‑01?", 1),
    ],
)
def test_supported_trade_questions(question: str, count: int, dataset, schema) -> None:  # type: ignore[no-untyped-def]
    parsed = parse_trade_query(question, schema)
    assert parsed.matched
    assert len(run_trade_query(parsed, dataset)) == count


def test_document_questions_are_not_treated_as_trade_queries(schema) -> None:  # type: ignore[no-untyped-def]
    assert not parse_trade_query("Give me the paragraph that defines the LEI requirement under MiFID II", schema).matched
    assert not parse_trade_query("Show the latest FCA guidance that mentions FX trades", schema).matched


# ----------------------------------------------------------------------------- selected rules combined with AND


def _row(trade: str, rule: str, status: str) -> dict:
    return {
        "trade_id": trade,
        "asset_class": "Equity",
        "regulator": "X",
        "rule_id": rule,
        "status": status,
        "affected_fields": [],
        "explanation": f"{rule} {status}",
    }


def test_and_combination_truth_table() -> None:
    rows = [
        _row("A", "R1", "PASS"), _row("A", "R2", "PASS"),  # all pass -> PASS
        _row("B", "R1", "PASS"), _row("B", "R2", "FAIL"),  # one fails -> FAIL
        _row("C", "R1", "ERROR"), _row("C", "R2", "FAIL"),  # FAIL wins over ERROR (false AND unknown = false)
        _row("D", "R1", "ERROR"), _row("D", "R2", "PASS"),  # unknown, nothing false -> ERROR
        _row("E", "R1", "NOT_APPLICABLE"), _row("E", "R2", "PASS"),  # N/A counts as satisfied -> PASS
        _row("F", "R1", "NOT_APPLICABLE"), _row("F", "R2", "NOT_APPLICABLE"),  # nothing applies
    ]  # fmt: skip
    verdicts = {v["trade_id"]: v for v in combine_and(rows, ["R1", "R2"])}
    assert {t: v["overall"] for t, v in verdicts.items()} == {
        "A": "PASS", "B": "FAIL", "C": "FAIL", "D": "ERROR", "E": "PASS", "F": "NOT_APPLICABLE"
    }  # fmt: skip
    assert [t for t, v in verdicts.items() if v["compliant"]] == ["A", "E", "F"]
    assert verdicts["B"]["failed_rule_ids"] == ["R2"] and verdicts["B"]["failures"][0]["explanation"] == "R2 FAIL"
    assert verdicts["C"]["error_rule_ids"] == ["R1"]
    summary = combined_summary(list(verdicts.values()), ["R1", "R2"])
    assert summary["expression"] == "R1 AND R2" and summary["logic"] == "AND"
    assert (summary["compliant_trades"], summary["non_compliant_trades"], summary["undetermined_trades"]) == (3, 2, 1)


def test_all_rules_combined_with_and_on_supplied_data(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    rule_list = list(rules.values())
    rows = evaluate_matrix(dataset, rule_list)
    combined = summarize(rows, dataset, rule_list)["combined"]
    assert combined["expression"] == "EMIR-1 AND EMIR-2 AND FCA-1 AND FCA-2 AND MIFID-1 AND MIFID-2 AND MIFID-3 AND MIFID-4"
    assert combined["status_counts"] == {"PASS": 44, "FAIL": 156, "NOT_APPLICABLE": 0, "ERROR": 0}
    assert combined["compliant_trades"] == 44 and combined["non_compliant_trades"] == 156
    verdicts = {v["trade_id"]: v for v in combine_and(rows, [r.id for r in rule_list])}
    t4 = verdicts["T000004"]
    assert t4["overall"] == "FAIL" and t4["failed_rule_ids"] == ["FCA-2", "MIFID-2"] and t4["rules_evaluated"] == 8
    t8 = verdicts["T000008"]  # FX trade: passes every rule that applies to it
    assert t8["overall"] == "PASS" and t8["not_applicable_rule_ids"] == ["EMIR-1", "FCA-2", "MIFID-3"]
    assert list(verdicts) == [t["Trade_ID"] for t in dataset.trades]  # dataset order


def test_selected_subset_is_combined_with_and(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    selected = select_rules(list(rules.values()), rule_ids=["EMIR-1", "EMIR-2", "FCA-1"])
    verdicts = combine_and(evaluate_matrix(dataset, selected), [r.id for r in selected])
    counts = combined_summary(verdicts, [r.id for r in selected])["status_counts"]
    assert counts == {"PASS": 179, "FAIL": 21, "NOT_APPLICABLE": 0, "ERROR": 0}
    t13 = next(v for v in verdicts if v["trade_id"] == "T000013")
    assert t13["failed_rule_ids"] == ["EMIR-1", "EMIR-2"]
    # A derivatives-only rule on its own: equities are "no rule applies", which is not a failure.
    only = select_rules(list(rules.values()), rule_ids=["EMIR-1"])
    single = {v["trade_id"]: v["overall"] for v in combine_and(evaluate_matrix(dataset, only), ["EMIR-1"])}
    assert single["T000001"] == "NOT_APPLICABLE" and single["T000002"] == "PASS"
    assert sum(1 for o in single.values() if o == "FAIL") == 5


def test_verdict_and_summary_csv(dataset, rules) -> None:  # type: ignore[no-untyped-def]
    rule_list = list(rules.values())
    rows = evaluate_matrix(dataset, rule_list)
    s = summarize(rows, dataset, rule_list)
    verdicts = combine_and(rows, [r.id for r in rule_list])
    parsed = list(csv.reader(io.StringIO(verdict_csv(verdicts, s["combined"]["expression"]))))
    assert parsed[0] == VERDICT_COLUMNS and len(parsed) == 201
    t4 = next(r for r in parsed if r[0] == "T000004")
    assert t4[2] == "FAIL" and t4[3] == "no" and t4[6] == "FCA-2, MIFID-2"
    combined_row = next(r for r in csv.reader(io.StringIO(summary_csv(s))) if r[0].startswith("Trades (rules combined with AND)"))
    assert combined_row[2:] == ["44", "156", "0", "0", "156"]
