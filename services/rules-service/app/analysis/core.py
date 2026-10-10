"""Pure analysis functions: Impact Matrix rows, summaries, gap analysis and checklists.

These functions take loaded rules and a trade dataset and return plain
dictionaries. Persistence and HTTP live elsewhere, so the logic is testable
without a database or web framework. Output order is deterministic: trades
in file order, rules in rule-set file order.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..engine import ERROR, FAIL, NOT_APPLICABLE, PASS, Rule, evaluate_rule
from ..engine.dataset import SchemaFinding, TradeDataset

CATEGORY_LABELS = {
    "missing_value": "Missing required values",
    "invalid_format": "Invalid field formats",
    "value_not_allowed": "Values outside an allowed list (e.g. unsupported currency)",
    "negative_value": "Negative numeric values",
    "numeric_constraint": "Numeric bound violations (e.g. zero quantity)",
    "date_constraint": "Date / timestamp constraints",
    "value_mismatch": "Value mismatches",
    "constant": "Constant-false rule branches",
}


def select_rules(rules: list[Rule], regulators: list[str] | None = None, rule_ids: list[str] | None = None) -> list[Rule]:
    regs = {r.lower() for r in regulators or []}
    ids = {r.upper() for r in rule_ids or []}
    selected = []
    for rule in rules:
        if regs and rule.regulator.lower() not in regs:
            continue
        if ids and rule.id.upper() not in ids:
            continue
        selected.append(rule)
    return selected


def evaluate_matrix(dataset: TradeDataset, rules: list[Rule]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in dataset.trades:
        for rule in rules:
            result = evaluate_rule(rule, trade)
            rows.append(
                {
                    "trade_id": str(trade.get("Trade_ID")),
                    "asset_class": trade.get("Asset_Class"),
                    "regulator": rule.regulator,
                    "rule_id": rule.id,
                    "rule_description": rule.description,
                    "status": result.status,
                    "affected_fields": result.affected_fields,
                    "actual_values": result.actual_values,
                    "expected_condition": result.expected_condition,
                    "explanation": result.explanation,
                    "rule_source": rule.rule_source,
                    "severity": rule.severity,
                    "category": result.category,
                    "conditional": result.conditional,
                }
            )
    return rows


AND_LOGIC = "AND"


def combine_and(rows: list[dict[str, Any]], rule_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """One verdict per trade: the selected rules combined with AND.

    A trade is compliant only if it satisfies every selected rule:

    * ``FAIL`` if any selected rule fails (AND with a false operand is false);
    * otherwise ``ERROR`` if any rule could not be evaluated (the result is unknown);
    * otherwise ``PASS`` if at least one rule applied and every applicable rule passed;
    * otherwise ``NOT_APPLICABLE`` (none of the selected rules applies to the trade).

    A NOT_APPLICABLE rule (its condition is not triggered, e.g. a derivatives-only
    rule on an equity trade) counts as satisfied, so it never makes a trade fail.
    Trades are returned in dataset order; rule ids keep rule-set order.
    """
    order = rule_ids if rule_ids is not None else list(dict.fromkeys(r["rule_id"] for r in rows))
    rank = {rid: i for i, rid in enumerate(order)}
    trades: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = trades.setdefault(
            r["trade_id"],
            {
                "trade_id": r["trade_id"],
                "asset_class": r.get("asset_class"),
                PASS: [],
                FAIL: [],
                ERROR: [],
                NOT_APPLICABLE: [],
                "failures": [],
            },
        )
        t[r["status"]].append(r["rule_id"])
        if r["status"] in (FAIL, ERROR):
            t["failures"].append(
                {
                    "rule_id": r["rule_id"],
                    "regulator": r.get("regulator"),
                    "status": r["status"],
                    "affected_fields": r.get("affected_fields") or [],
                    "explanation": r.get("explanation"),
                }
            )

    def ordered(ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda rid: rank.get(rid, len(rank)))

    out = []
    for t in trades.values():
        if t[FAIL]:
            overall = FAIL
        elif t[ERROR]:
            overall = ERROR
        elif t[PASS]:
            overall = PASS
        else:
            overall = NOT_APPLICABLE
        evaluated = len(t[PASS]) + len(t[FAIL]) + len(t[ERROR]) + len(t[NOT_APPLICABLE])
        if overall == FAIL:
            reason = f"Fails {len(t[FAIL])} of {evaluated} selected rule(s): {', '.join(ordered(t[FAIL]))}."
        elif overall == ERROR:
            reason = f"No rule fails, but {', '.join(ordered(t[ERROR]))} could not be evaluated, so compliance is undetermined."
        elif overall == PASS:
            reason = f"Satisfies all {evaluated} selected rule(s)" + (
                f" ({', '.join(ordered(t[NOT_APPLICABLE]))} not applicable)." if t[NOT_APPLICABLE] else "."
            )
        else:
            reason = "None of the selected rules applies to this trade."
        out.append(
            {
                "trade_id": t["trade_id"],
                "asset_class": t["asset_class"],
                "overall": overall,
                "compliant": overall in (PASS, NOT_APPLICABLE),
                "rules_evaluated": evaluated,
                "failed_rule_ids": ordered(t[FAIL]),
                "error_rule_ids": ordered(t[ERROR]),
                "passed_rule_ids": ordered(t[PASS]),
                "not_applicable_rule_ids": ordered(t[NOT_APPLICABLE]),
                "failures": sorted(t["failures"], key=lambda f: rank.get(f["rule_id"], len(rank))),
                "reason": reason,
            }
        )
    return out


def combined_summary(verdicts: list[dict[str, Any]], rule_ids: list[str]) -> dict[str, Any]:
    counts = Counter(v["overall"] for v in verdicts)
    total = len(verdicts)
    compliant = counts[PASS] + counts[NOT_APPLICABLE]
    return {
        "logic": AND_LOGIC,
        "rule_ids": rule_ids,
        "expression": f" {AND_LOGIC} ".join(rule_ids),
        "description": "A trade is compliant only if it satisfies every selected rule; failing any one makes it non-compliant. "
        "Rules that do not apply to a trade count as satisfied.",
        "trades": total,
        "status_counts": {s: counts.get(s, 0) for s in (PASS, FAIL, NOT_APPLICABLE, ERROR)},
        "compliant_trades": compliant,
        "non_compliant_trades": counts[FAIL],
        "undetermined_trades": counts[ERROR],
        "compliance_rate": round(compliant / total, 4) if total else None,
    }


def summarize(rows: list[dict[str, Any]], dataset: TradeDataset, rules: list[Rule]) -> dict[str, Any]:
    status_counts = Counter(r["status"] for r in rows)
    failed_trades = {r["trade_id"] for r in rows if r["status"] == FAIL}
    error_trades = {r["trade_id"] for r in rows if r["status"] == ERROR}
    clean_trades = dataset.count - len(failed_trades | error_trades)

    by_reg: dict[str, Counter[str]] = defaultdict(Counter)
    reg_impacted: dict[str, set[str]] = defaultdict(set)
    by_rule: dict[str, Counter[str]] = defaultdict(Counter)
    by_asset: dict[str, Counter[str]] = defaultdict(Counter)
    asset_trades: dict[str, set[str]] = defaultdict(set)
    asset_impacted: dict[str, set[str]] = defaultdict(set)
    trade_fails: dict[str, list[str]] = defaultdict(list)
    by_category: Counter[str] = Counter()
    for r in rows:
        by_reg[r["regulator"]][r["status"]] += 1
        by_rule[r["rule_id"]][r["status"]] += 1
        asset = r["asset_class"] or "Unknown"
        asset_trades[asset].add(r["trade_id"])
        by_asset[asset][r["status"]] += 1
        if r["status"] == FAIL:
            reg_impacted[r["regulator"]].add(r["trade_id"])
            asset_impacted[asset].add(r["trade_id"])
            trade_fails[r["trade_id"]].append(r["rule_id"])
            by_category[r["category"] or "value_mismatch"] += 1

    rule_meta = {rule.id: rule for rule in rules}
    return {
        "total_trades": dataset.count,
        "total_rules": len(rules),
        "total_evaluations": len(rows),
        "status_counts": {s: status_counts.get(s, 0) for s in (PASS, FAIL, NOT_APPLICABLE, ERROR)},
        "unique_impacted_trades": len(failed_trades),
        "trades_with_errors": len(error_trades),
        "fully_compliant_trades": clean_trades,
        "trade_compliance_rate": round(clean_trades / dataset.count, 4) if dataset.count else None,
        "by_regulator": [
            {
                "regulator": reg,
                "pass": c[PASS],
                "fail": c[FAIL],
                "not_applicable": c[NOT_APPLICABLE],
                "error": c[ERROR],
                "impacted_trades": len(reg_impacted[reg]),
            }
            for reg, c in sorted(by_reg.items())
        ],
        "by_rule": [
            {
                "rule_id": rid,
                "regulator": rule_meta[rid].regulator if rid in rule_meta else None,
                "description": rule_meta[rid].description if rid in rule_meta else None,
                "severity": rule_meta[rid].severity if rid in rule_meta else None,
                "pass": c[PASS],
                "fail": c[FAIL],
                "not_applicable": c[NOT_APPLICABLE],
                "error": c[ERROR],
            }
            for rid, c in ((rule.id, by_rule[rule.id]) for rule in rules)
        ],
        "by_asset_class": [
            {
                "asset_class": asset,
                "trades": len(asset_trades[asset]),
                "impacted_trades": len(asset_impacted[asset]),
                "fail": c[FAIL],
            }
            for asset, c in sorted(by_asset.items())
        ],
        "by_category": [{"category": cat, "label": CATEGORY_LABELS.get(cat, cat), "count": n} for cat, n in by_category.most_common()],
        "top_impacted_trades": [
            {"trade_id": tid, "fail_count": len(rids), "rule_ids": rids}
            for tid, rids in sorted(trade_fails.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:10]
        ],
        # The selected rules combined with AND: one verdict per trade.
        "combined": combined_summary(combine_and(rows, [rule.id for rule in rules]), [rule.id for rule in rules]),
    }


def gap_analysis(rows: list[dict[str, Any]], schema_findings: list[SchemaFinding] | None, max_trade_ids: int = 50) -> dict[str, Any]:
    """Group rule failures by failure category; report schema findings separately."""
    groups: dict[str, dict[str, Any]] = {}
    conditional: dict[str, Any] = {"count": 0, "trades": set(), "rules": set()}
    for r in rows:
        if r["status"] != FAIL:
            continue
        cat = r["category"] or "value_mismatch"
        g = groups.setdefault(
            cat,
            {
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, cat),
                "count": 0,
                "trades": [],
                "rules": set(),
                "fields": set(),
                "examples": [],
            },
        )
        g["count"] += 1
        if r["trade_id"] not in g["trades"]:
            g["trades"].append(r["trade_id"])
        g["rules"].add(r["rule_id"])
        g["fields"].update(r["affected_fields"])
        if len(g["examples"]) < 3:
            g["examples"].append({"trade_id": r["trade_id"], "rule_id": r["rule_id"], "explanation": r["explanation"]})
        if r["conditional"]:
            conditional["count"] += 1
            conditional["trades"].add(r["trade_id"])
            conditional["rules"].add(r["rule_id"])

    rule_groups = []
    for g in sorted(groups.values(), key=lambda x: -x["count"]):
        rule_groups.append(
            {
                "category": g["category"],
                "label": g["label"],
                "failed_evaluations": g["count"],
                "impacted_trades": len(g["trades"]),
                "trade_ids": g["trades"][:max_trade_ids],
                "rule_ids": sorted(g["rules"]),
                "fields": sorted(g["fields"]),
                "examples": g["examples"],
            }
        )

    schema_section: dict[str, Any] = {"enabled": schema_findings is not None, "total": 0, "by_check": []}
    if schema_findings is not None:
        buckets: dict[tuple[str, str], list[SchemaFinding]] = defaultdict(list)
        for f in schema_findings:
            buckets[(f.field, f.check)].append(f)
        schema_section["total"] = len(schema_findings)
        schema_section["impacted_trades"] = len({f.trade_id for f in schema_findings})
        schema_section["by_check"] = [
            {
                "field": fld,
                "check": chk,
                "count": len(items),
                "trade_ids": [i.trade_id for i in items][:max_trade_ids],
                "example": items[0].message,
            }
            for (fld, chk), items in sorted(buckets.items(), key=lambda kv: -len(kv[1]))
        ]
    return {
        "rule_findings": {
            "total_failed_evaluations": sum(g["failed_evaluations"] for g in rule_groups),
            "impacted_trades": len({t for g in groups.values() for t in g["trades"]}),
            "by_category": rule_groups,
            "conditional_requirements": {
                "failed_evaluations": conditional["count"],
                "impacted_trades": len(conditional["trades"]),
                "rule_ids": sorted(conditional["rules"]),
            },
        },
        "schema_findings": schema_section,
    }


def applicability_text(rule: Rule) -> str:
    from ..engine.expressions import operator_of
    from ..engine.render import render

    if rule.applies_when is not None:
        return f"Only when {render(rule.applies_when)}"
    node = operator_of(rule.logic) if isinstance(rule.logic, dict) else None
    if node and node[0] in {"if", "?:"}:
        return f"Conditional: {render(rule.logic)}"
    return "All trades"


def checklist(rows: list[dict[str, Any]], rules: list[Rule], trade_id: str | None = None) -> dict[str, Any]:
    """Per-rule checklist; aggregated over all trades, or for one trade."""
    items = []
    if trade_id is not None:
        by_rule = {r["rule_id"]: r for r in rows if r["trade_id"] == trade_id}
        for rule in rules:
            r = by_rule.get(rule.id)
            if r is None:
                continue
            items.append(
                {
                    "rule_id": rule.id,
                    "regulator": rule.regulator,
                    "description": rule.description,
                    "applicability": applicability_text(rule),
                    "status": r["status"],
                    "explanation": r["explanation"],
                    "affected_fields": r["affected_fields"],
                    "actual_values": r["actual_values"],
                    "rule_source": rule.rule_source,
                }
            )
        counts = Counter(i["status"] for i in items)
        return {"scope": "trade", "trade_id": trade_id, "items": items, "status_counts": dict(counts)}

    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, str] = {}
    for r in rows:
        grouped[r["rule_id"]][r["status"]] += 1
        if r["status"] == FAIL and r["rule_id"] not in examples:
            examples[r["rule_id"]] = f"{r['trade_id']}: {r['explanation']}"
    for rule in rules:
        c = grouped.get(rule.id, Counter())
        applicable = c[PASS] + c[FAIL] + c[ERROR]
        if c[ERROR]:
            status = "ERROR"
        elif applicable == 0:
            status = "NOT_APPLICABLE"
        elif c[FAIL]:
            status = "NON_COMPLIANT"
        else:
            status = "COMPLIANT"
        if status == "COMPLIANT":
            explanation = f"All {applicable} applicable trade(s) satisfy the rule."
        elif status == "NON_COMPLIANT":
            explanation = f"{c[FAIL]} of {applicable} applicable trade(s) fail. Example — {examples.get(rule.id, '')}"
        elif status == "NOT_APPLICABLE":
            explanation = "The rule does not apply to any trade in the dataset."
        else:
            explanation = f"{c[ERROR]} evaluation error(s); results for this rule are incomplete."
        items.append(
            {
                "rule_id": rule.id,
                "regulator": rule.regulator,
                "description": rule.description,
                "applicability": applicability_text(rule),
                "status": status,
                "pass": c[PASS],
                "fail": c[FAIL],
                "not_applicable": c[NOT_APPLICABLE],
                "error": c[ERROR],
                "applicable": applicable,
                "compliance_rate": round(c[PASS] / applicable, 4) if applicable else None,
                "explanation": explanation,
                "rule_source": rule.rule_source,
            }
        )
    regs: dict[str, Counter[str]] = defaultdict(Counter)
    for i in items:
        regs[i["regulator"]][i["status"]] += 1
    return {
        "scope": "dataset",
        "items": items,
        "by_regulator": [{"regulator": k, **dict(v)} for k, v in sorted(regs.items())],
    }
