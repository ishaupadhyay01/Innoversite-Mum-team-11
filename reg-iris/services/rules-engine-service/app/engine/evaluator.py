"""Evaluate rules against one trade and classify the outcome.

Status semantics
* PASS            — the rule applies and its logic is satisfied.
* FAIL            — the rule applies and its logic is violated (explanation says exactly why).
* NOT_APPLICABLE  — ``applies_when`` is false, or the rule is a top-level ``if`` whose chosen
                    branch is the literal ``true`` (e.g. MIFID-3 for non-derivatives, FCA-2 for FX).
* ERROR           — the logic could not be evaluated (e.g. division by zero, bad data type).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .explain import describe, describe_condition
from .jsonlogic import Data, JsonLogic, JsonLogicError, truthy
from .operations import ENGINE


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RuleSpec:
    code: str
    regulator: str
    description: str
    logic: Any
    impact: str | None = None
    severity: str = "HIGH"
    applies_when: Any = None
    fields: tuple[str, ...] = ()
    clause_ref: str | None = None
    citation: str | None = None
    rule_id: str | None = None  # DB id, when loaded from storage


@dataclass
class Outcome:
    rule_code: str
    status: Status
    explanation: str
    field_values: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


def _literal_true_branch(engine: JsonLogic, logic: Any, data: Data) -> tuple[bool, str | None]:
    """For {"if": [cond, then, else]}: was the chosen branch the literal `true`?"""
    if not (engine.is_logic(logic) and next(iter(logic)) in ("if", "?:")):
        return False, None
    args = logic[next(iter(logic))]
    i = 0
    while i < len(args) - 1:
        if truthy(engine.apply(args[i], data)):
            return args[i + 1] is True, describe_condition(engine, args[i], data)
        i += 2
    if i < len(args) and args[i] is True:
        conds = [describe(engine, args[j], data) for j in range(0, len(args) - 1, 2)]
        return True, "scope condition not met — " + "; ".join(conds)
    return False, None


def _cite(rule: RuleSpec) -> str:
    where = f" ({rule.citation})" if rule.citation else (f" ({rule.clause_ref})" if rule.clause_ref else "")
    return f"{rule.regulator} rule {rule.code}{where}"


def evaluate_rule(rule: RuleSpec, trade: Data, engine: JsonLogic = ENGINE) -> Outcome:
    values = {f: trade.get(f) for f in rule.fields}
    try:
        if rule.applies_when is not None and not truthy(engine.apply(rule.applies_when, trade)):
            why = describe(engine, rule.applies_when, trade)
            return Outcome(rule.code, Status.NOT_APPLICABLE, f"Not applicable: {why}.", values, why)
        exempt, why = _literal_true_branch(engine, rule.logic, trade)
        if exempt:
            return Outcome(rule.code, Status.NOT_APPLICABLE, f"Not applicable under {_cite(rule)}: {why}.", values, why)
        if truthy(engine.apply(rule.logic, trade)):
            return Outcome(rule.code, Status.PASS, f"Complies with {_cite(rule)}: {rule.description}", values)
        reason = describe(engine, rule.logic, trade)
        impact = f" {rule.impact}" if rule.impact else ""
        return Outcome(
            rule.code,
            Status.FAIL,
            f"{reason[0].upper()}{reason[1:]} — required by {_cite(rule)}.{impact}",
            values,
            reason,
        )
    except (JsonLogicError, TypeError, ValueError, ZeroDivisionError) as exc:
        return Outcome(rule.code, Status.ERROR, f"Rule {rule.code} could not be evaluated: {exc}", values, str(exc))


def evaluate_trade(trade: Data, rules: list[RuleSpec], engine: JsonLogic = ENGINE) -> list[Outcome]:
    return [evaluate_rule(rule, trade, engine) for rule in rules]
