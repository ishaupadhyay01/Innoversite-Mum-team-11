"""Generic JSON rule engine: loading, normalisation, evaluation and explanation."""

from .expressions import EvaluationError, RuleExpressionError, evaluate, truthy, validate_expression
from .loader import Rule, RuleSet, build_rule_set, load_rule_sets
from .normalization import Overlay, normalize_logic, normalize_schema
from .runner import ERROR, FAIL, NOT_APPLICABLE, PASS, STATUSES, RuleEvaluation, evaluate_rule

__all__ = [
    "ERROR",
    "FAIL",
    "NOT_APPLICABLE",
    "PASS",
    "STATUSES",
    "EvaluationError",
    "Overlay",
    "Rule",
    "RuleEvaluation",
    "RuleExpressionError",
    "RuleSet",
    "build_rule_set",
    "evaluate",
    "evaluate_rule",
    "load_rule_sets",
    "normalize_logic",
    "normalize_schema",
    "truthy",
    "validate_expression",
]
