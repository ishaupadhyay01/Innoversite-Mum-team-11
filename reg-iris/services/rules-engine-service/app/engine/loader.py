"""Parse + validate an uploaded rule file into RuleSpecs and lint findings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from .evaluator import RuleSpec
from .jsonlogic import JsonLogic
from .linter import LintIssue, lint_rule
from .operations import ENGINE

_SCHEMA = json.loads((Path(__file__).parent / "rule_file.schema.json").read_text())


class RuleFileError(ValueError):
    def __init__(self, message: str, issues: list[LintIssue] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


@dataclass
class LoadedRuleFile:
    regulator: str
    jurisdiction: str | None
    raw: dict[str, Any]
    rules: list[RuleSpec]
    issues: list[LintIssue]


def load_rule_file(
    content: bytes | str | dict[str, Any], known_fields: set[str], engine: JsonLogic = ENGINE
) -> LoadedRuleFile:
    if isinstance(content, dict):
        raw = content
    else:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuleFileError(f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    validator = jsonschema.Draft7Validator(_SCHEMA)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        issues = [LintIssue("ERROR", None, f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}") for e in errors]
        raise RuleFileError("Rule file does not match the rule schema", issues)

    issues: list[LintIssue] = []
    rules: list[RuleSpec] = []
    seen: set[str] = set()
    for r in raw["rules"]:
        if r["id"] in seen:
            issues.append(LintIssue("ERROR", r["id"], "Duplicate rule id"))
        seen.add(r["id"])
        issues += lint_rule(engine, r["id"], r["logic"], r.get("applies_when"), known_fields)
        if r.get("enabled", True) is False:
            continue
        fields = tuple(
            dict.fromkeys(
                engine.referenced_vars(r["logic"])
                + engine.referenced_vars(r.get("applies_when"))
                + sorted(_regex_fields(r["logic"]))
            )
        )
        rules.append(
            RuleSpec(
                code=r["id"],
                regulator=raw["regulator"],
                description=r["description"],
                logic=r["logic"],
                impact=r.get("impact"),
                severity=r.get("severity", "HIGH"),
                applies_when=r.get("applies_when"),
                fields=fields,
                clause_ref=(r.get("source") or {}).get("clause_ref"),
            )
        )
    if any(i.level == "ERROR" for i in issues):
        raise RuleFileError("Rule file has errors", issues)
    return LoadedRuleFile(raw["regulator"], raw.get("jurisdiction"), raw, rules, issues)


def _regex_fields(node: Any) -> set[str]:
    from .linter import _regex_field_refs

    return _regex_field_refs(ENGINE, node)
