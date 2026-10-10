"""Rules engine core: pure functions, no I/O. Fully unit-testable and reusable from any service."""

from .evaluator import Outcome, RuleSpec, Status, evaluate_rule, evaluate_trade
from .loader import RuleFileError, load_rule_file
from .operations import ENGINE

__all__ = [
    "ENGINE",
    "Outcome",
    "RuleFileError",
    "RuleSpec",
    "Status",
    "evaluate_rule",
    "evaluate_trade",
    "load_rule_file",
]
