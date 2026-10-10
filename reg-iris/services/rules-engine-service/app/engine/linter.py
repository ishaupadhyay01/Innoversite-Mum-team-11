"""Static checks run when a rule file is uploaded. ERRORs block the upload; WARNINGs are shown in the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .jsonlogic import JsonLogic


@dataclass
class LintIssue:
    level: Literal["ERROR", "WARNING", "INFO"]
    rule_code: str | None
    message: str


def lint_rule(engine: JsonLogic, code: str, logic: Any, applies_when: Any, known_fields: set[str]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for expr in (logic, applies_when):
        if expr is None:
            continue
        for op in sorted(engine.unknown_operators(expr)):
            issues.append(LintIssue("ERROR", code, f"Unknown operator '{op}'"))
    fields = set(engine.referenced_vars(logic)) | set(engine.referenced_vars(applies_when) if applies_when else [])
    fields |= _regex_field_refs(engine, logic)
    for f in sorted(fields - known_fields):
        issues.append(
            LintIssue(
                "WARNING",
                code,
                f"Field '{f}' is not in the trade reporting schema; " "trades will be treated as missing it",
            )
        )
    if engine.is_logic(logic) and next(iter(logic)) == "and" and applies_when is None:
        first = logic["and"][0] if logic["and"] else None
        if engine.is_logic(first) and next(iter(first)) in ("==", "==="):
            issues.append(
                LintIssue(
                    "WARNING",
                    code,
                    "Rule starts with a scoping condition inside 'and' (e.g. Asset_Class == X). Every trade that does "
                    "not match the scope will FAIL. Move the condition to 'applies_when' or use {'if': [cond, check, true]}.",
                )
            )
    if _contains_double_dollar(logic):
        issues.append(
            LintIssue(
                "INFO",
                code,
                "Regex pattern contains '$$' (harmless double end-anchor; " "probably a template-escaping artefact)",
            )
        )
    return issues


def _regex_field_refs(engine: JsonLogic, node: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(node, list):
        for n in node:
            out |= _regex_field_refs(engine, n)
    elif engine.is_logic(node):
        op, args = next(iter(node.items()))
        if op == "regex" and isinstance(args, list) and args and isinstance(args[0], str):
            out.add(args[0])
        out |= _regex_field_refs(engine, args)
    return out


def _contains_double_dollar(node: Any) -> bool:
    if isinstance(node, str):
        return "$$" in node
    if isinstance(node, list):
        return any(_contains_double_dollar(n) for n in node)
    if isinstance(node, dict):
        return any(_contains_double_dollar(v) for v in node.values())
    return False
