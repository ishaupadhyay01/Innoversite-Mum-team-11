"""Evaluate one rule against one trade, with explicit applicability semantics.

Status values:

``NOT_APPLICABLE``
    * the rule's ``applies_when`` expression is false for the trade, or
    * the rule's top-level logic is an ``if`` whose selected branch is the
      literal ``true`` — i.e. the conditional requirement is not triggered
      (MIFID-3 for a non-derivative) or is explicitly waived (FCA-2 for FX).
``PASS``
    The logic evaluates truthy.
``FAIL``
    The logic evaluates falsy; the explanation names the failing condition and
    the actual field values.
``ERROR``
    The rule is invalid or could not be evaluated (type mismatch, bad data).
    Errors are never counted as compliant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .explain import Reason, why_false
from .expressions import EvaluationError, RuleExpressionError, evaluate, selected_if_branch, truthy
from .loader import Rule
from .render import render

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
ERROR = "ERROR"
STATUSES = (PASS, FAIL, NOT_APPLICABLE, ERROR)


@dataclass
class RuleEvaluation:
    status: str
    explanation: str
    reasons: list[Reason] = field(default_factory=list)
    affected_fields: list[str] = field(default_factory=list)
    actual_values: dict[str, Any] = field(default_factory=dict)
    expected_condition: str = ""
    category: str | None = None
    conditional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "explanation": self.explanation,
            "reasons": [r.as_dict() for r in self.reasons],
            "affected_fields": self.affected_fields,
            "actual_values": self.actual_values,
            "expected_condition": self.expected_condition,
            "category": self.category,
            "conditional": self.conditional,
        }


def _sentence(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _values(trade: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {f: trade.get(f) for f in fields}


def evaluate_rule(rule: Rule, trade: dict[str, Any]) -> RuleEvaluation:
    rule_fields = rule.fields
    if not rule.valid:
        return RuleEvaluation(
            ERROR,
            "Rule configuration is invalid: " + "; ".join(rule.errors),
            affected_fields=rule_fields,
            actual_values=_values(trade, rule_fields),
            expected_condition=render(rule.logic) if rule.logic is not None else "",
        )
    try:
        if rule.applies_when is not None and not truthy(evaluate(rule.applies_when, trade)):
            fields = rule_fields
            return RuleEvaluation(
                NOT_APPLICABLE,
                f"Not applicable: applicability condition {render(rule.applies_when)} does not hold "
                f"({', '.join(f'{f} = {trade.get(f)!r}' for f in _applies_fields(rule))}).",
                affected_fields=[],
                actual_values=_values(trade, fields),
                expected_condition=render(rule.applies_when),
            )

        branch_index, branch = selected_if_branch(rule.logic, trade)
        if branch_index is not None and branch is True:
            return RuleEvaluation(
                NOT_APPLICABLE,
                _not_triggered_text(rule.logic, branch_index, trade),
                actual_values=_values(trade, rule_fields),
                expected_condition=render(rule.logic),
                conditional=True,
            )

        result = evaluate(rule.logic, trade)
        if truthy(result):
            return RuleEvaluation(
                PASS,
                f"Compliant: {render(rule.logic)} holds.",
                actual_values=_values(trade, rule_fields),
                expected_condition=render(rule.logic),
            )

        reasons = why_false(rule.logic, trade)
        affected: list[str] = []
        for r in reasons:
            for f in r.fields:
                if f not in affected:
                    affected.append(f)
        detail = (
            "; ".join((f"Because {r.conditional}: " if r.conditional else "") + r.message for r in reasons)
            or f"{render(rule.logic)} does not hold"
        )
        explanation = _sentence(detail)
        impact = _sentence(rule.impact)
        if impact:
            explanation = f"{explanation} Rule impact: {impact}"
        return RuleEvaluation(
            FAIL,
            explanation,
            reasons=reasons,
            affected_fields=affected or rule_fields,
            actual_values=_values(trade, affected or rule_fields),
            expected_condition="; ".join(r.expected for r in reasons) or render(rule.logic),
            category=reasons[0].category if reasons else None,
            conditional=any(r.conditional for r in reasons),
        )
    except (EvaluationError, RuleExpressionError) as exc:
        return RuleEvaluation(
            ERROR,
            f"Evaluation error: {exc}",
            affected_fields=rule_fields,
            actual_values=_values(trade, rule_fields),
            expected_condition=render(rule.logic),
        )


def _applies_fields(rule: Rule) -> list[str]:
    from .expressions import fields_in

    return fields_in(rule.applies_when)


def _not_triggered_text(logic: Any, branch_index: int, trade: dict[str, Any]) -> str:
    from .expressions import fields_in, operator_of

    node = operator_of(logic)
    assert node is not None
    _, args = node
    if branch_index % 2 == 1:
        cond = args[branch_index - 1]
        values = ", ".join(f"{f} = {trade.get(f)!r}" for f in fields_in(cond))
        return (
            f"Not applicable: condition {render(cond)} holds ({values}) and the rule requires nothing "
            "further for this case (branch is the constant true)."
        )
    conds = [args[i] for i in range(0, branch_index, 2)]
    fields: list[str] = []
    for c in conds:
        for f in fields_in(c):
            if f not in fields:
                fields.append(f)
    values = ", ".join(f"{f} = {trade.get(f)!r}" for f in fields)
    cond_text = " / ".join(render(c) for c in conds)
    return f"Not applicable: conditional requirement not triggered — {cond_text} does not hold ({values})."
