"""Loading and validating JSON rule sets (zero-code rule updates).

Every ``*.json`` file in the rules directory is a rule set::

    {
      "regulator": "MiFID II",
      "jurisdiction": "EU",
      "rules": [
        {
          "id": "MIFID-2",
          "description": "Price must be non-negative.",
          "logic": {">=": [{"var": "Price"}, 0]},
          "impact": "Field Price cannot be negative.",
          "severity": "high",             # optional
          "applies_when": {...},          # optional applicability expression
          "citation": {"document": "...", "clause": "..."}   # optional, shown verbatim
        }
      ]
    }

Dropping a new file into the directory and calling ``POST /api/rules/reload``
makes its rules available — no Python changes.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iris_shared.text import sha256_bytes

from .expressions import fields_in, validate_expression
from .normalization import Overlay, normalize_logic
from .render import render


@dataclass
class Rule:
    id: str
    regulator: str
    jurisdiction: str | None
    description: str
    impact: str | None
    source_file: str
    source_logic: Any
    logic: Any
    severity: str | None = None
    applies_when: Any = None
    applies_when_source: str | None = None  # "rule" | "overlay"
    applies_when_rationale: str | None = None
    citation: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def fields(self) -> list[str]:
        out = fields_in(self.logic)
        for f in fields_in(self.applies_when) if self.applies_when is not None else []:
            if f not in out:
                out.append(f)
        return out

    @property
    def rule_source(self) -> str:
        return f"{self.source_file}#{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "regulator": self.regulator,
            "jurisdiction": self.jurisdiction,
            "description": self.description,
            "impact": self.impact,
            "severity": self.severity,
            "source_file": self.source_file,
            "rule_source": self.rule_source,
            "source_logic": self.source_logic,
            "logic": self.logic,
            "logic_text": render(self.logic),
            "applies_when": self.applies_when,
            "applies_when_text": render(self.applies_when) if self.applies_when is not None else None,
            "applies_when_source": self.applies_when_source,
            "applies_when_rationale": self.applies_when_rationale,
            "citation": self.citation,
            "fields": self.fields,
            "normalization_notes": self.notes,
            "errors": self.errors,
            "warnings": self.warnings,
            "valid": self.valid,
        }


@dataclass
class RuleSet:
    file_name: str
    regulator: str
    jurisdiction: str | None
    rules: list[Rule]
    content_hash: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and all(r.valid for r in self.rules)

    def to_dict(self, include_rules: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "file_name": self.file_name,
            "regulator": self.regulator,
            "jurisdiction": self.jurisdiction,
            "rule_count": len(self.rules),
            "content_hash": self.content_hash,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }
        if include_rules:
            data["rules"] = [r.to_dict() for r in self.rules]
        return data


def build_rule_set(obj: Any, file_name: str, raw_bytes: bytes, known_fields: set[str], overlay: Overlay) -> RuleSet:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(obj, dict):
        return RuleSet(file_name, "Unknown", None, [], sha256_bytes(raw_bytes), errors=["rule file must be a JSON object"])
    regulator = str(obj.get("regulator") or "").strip()
    if not regulator:
        errors.append("missing 'regulator'")
        regulator = "Unknown"
    jurisdiction = obj.get("jurisdiction")
    raw_rules = obj.get("rules")
    if not isinstance(raw_rules, list):
        errors.append("'rules' must be a list")
        raw_rules = []

    rules: list[Rule] = []
    for index, raw in enumerate(raw_rules):
        where = f"rules[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: rule must be an object")
            continue
        rule_id = str(raw.get("id") or "").strip()
        rule_errors: list[str] = []
        rule_warnings: list[str] = []
        if not rule_id:
            rule_errors.append("missing 'id'")
            rule_id = f"{Path(file_name).stem}-{index + 1}"
        if "logic" not in raw:
            rule_errors.append("missing 'logic'")
        description = str(raw.get("description") or "").strip()
        if not description:
            rule_warnings.append("missing 'description'")

        source_logic = copy.deepcopy(raw.get("logic"))
        logic, notes = normalize_logic(source_logic, known_fields, overlay.field_aliases)
        rule_errors.extend(validate_expression(logic))
        if '"toNumber"' in json.dumps(logic):
            notes.append(
                "toNumber: ISO dates (YYYY-MM-DD) convert to the integer YYYYMMDD so they can be compared "
                "numerically (documented engine extension; JSONLogic has no date type)"
            )

        applies_when = raw.get("applies_when")
        applies_source = "rule" if applies_when is not None else None
        rationale = raw.get("applies_when_rationale")
        overlay_entry = overlay.rules.get(rule_id) or {}
        if applies_when is None and overlay_entry.get("applies_when") is not None:
            applies_when = overlay_entry["applies_when"]
            applies_source = "overlay"
            rationale = overlay_entry.get("rationale")
            notes.append(
                f"applicability: declared in {overlay.source or 'overlay'} as {render(applies_when)}"
                + (f" — {rationale}" if rationale else "")
            )
        if applies_when is not None:
            applies_when, aw_notes = normalize_logic(applies_when, known_fields, overlay.field_aliases)
            notes.extend(aw_notes)
            rule_errors.extend(f"applies_when: {e}" for e in validate_expression(applies_when))

        for f in fields_in(logic) + (fields_in(applies_when) if applies_when is not None else []):
            if known_fields and f not in known_fields:
                rule_warnings.append(f"field {f!r} is not a known trade field; it will be treated as missing")

        citation = raw.get("citation") if isinstance(raw.get("citation"), dict) else None
        rules.append(
            Rule(
                id=rule_id,
                regulator=regulator,
                jurisdiction=jurisdiction,
                description=description,
                impact=(str(raw["impact"]).strip() if raw.get("impact") else None),
                source_file=file_name,
                source_logic=source_logic,
                logic=logic,
                severity=(str(raw["severity"]) if raw.get("severity") else None),
                applies_when=applies_when,
                applies_when_source=applies_source,
                applies_when_rationale=rationale,
                citation=citation,
                notes=notes,
                errors=rule_errors,
                warnings=sorted(set(rule_warnings)),
            )
        )
    return RuleSet(
        file_name=file_name,
        regulator=regulator,
        jurisdiction=jurisdiction,
        rules=rules,
        content_hash=sha256_bytes(raw_bytes),
        errors=errors,
        warnings=warnings,
    )


def load_rule_sets(rules_dir: Path, known_fields: set[str], overlay: Overlay) -> list[RuleSet]:
    rule_sets: list[RuleSet] = []
    for path in sorted(rules_dir.glob("*.json")):
        raw = path.read_bytes()
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            rule_sets.append(RuleSet(path.name, "Unknown", None, [], sha256_bytes(raw), errors=[f"invalid JSON: {exc}"]))
            continue
        rule_sets.append(build_rule_set(obj, path.name, raw, known_fields, overlay))
    _flag_duplicate_ids(rule_sets)
    return rule_sets


def _flag_duplicate_ids(rule_sets: list[RuleSet]) -> None:
    seen: dict[str, str] = {}
    for rs in rule_sets:
        for rule in rs.rules:
            if rule.id in seen:
                rule.errors.append(f"duplicate rule id {rule.id!r} (also defined in {seen[rule.id]})")
            else:
                seen[rule.id] = rs.file_name
