from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import RuleFileError, RuleSpec, load_rule_file
from app.engine.linter import LintIssue
from app.models import Rule, RuleClauseLink, RuleSet
from app.trades.schema import ReportingSchema
from iris_common.errors import NotFoundError, ValidationFailedError
from iris_common.text import canonical_regulator, sha256_bytes


def _issues(issues: list[LintIssue]) -> list[dict]:
    return [i.__dict__ for i in issues]


def validate_rule_file(data: bytes, schema: ReportingSchema) -> tuple[bool, str | None, int, list[dict]]:
    try:
        loaded = load_rule_file(data, schema.names)
        return True, loaded.regulator, len(loaded.rules), _issues(loaded.issues)
    except RuleFileError as exc:
        return False, None, 0, _issues(exc.issues) or [{"level": "ERROR", "rule_code": None, "message": str(exc)}]


def upload_rule_set(
    db: Session,
    filename: str,
    data: bytes,
    schema: ReportingSchema,
    *,
    source_document_id: uuid.UUID | None,
    actor: str | None,
) -> tuple[RuleSet, bool]:
    """Store a rule file as the new ACTIVE rule set for its regulator. Identical re-uploads are idempotent."""
    sha = sha256_bytes(data)
    if existing := db.scalar(select(RuleSet).where(RuleSet.sha256 == sha)):
        return existing, True
    try:
        loaded = load_rule_file(data, schema.names)
    except RuleFileError as exc:
        raise ValidationFailedError(
            str(exc), code="INVALID_RULE_FILE", details={"issues": _issues(exc.issues)}
        ) from exc

    canonical = canonical_regulator(loaded.regulator) or ""
    version = (
        db.scalar(select(func.max(RuleSet.version_number)).where(RuleSet.regulator_canonical == canonical)) or 0
    ) + 1
    for old in db.scalars(select(RuleSet).where(RuleSet.regulator_canonical == canonical, RuleSet.status == "ACTIVE")):
        old.status = "INACTIVE"
    db.flush()
    rule_set = RuleSet(
        name=f"{loaded.regulator} rules v{version}",
        regulator=loaded.regulator,
        regulator_canonical=canonical,
        jurisdiction=loaded.jurisdiction,
        version_number=version,
        status="ACTIVE",
        source_filename=filename,
        sha256=sha,
        raw=loaded.raw,
        lint=_issues(loaded.issues),
        rule_count=len(loaded.rules),
        source_document_id=source_document_id,
        uploaded_by=actor,
    )
    for n, spec in enumerate(loaded.rules, 1):
        rule = Rule(
            ordinal=n,
            code=spec.code,
            description=spec.description,
            logic=spec.logic,
            applies_when=spec.applies_when,
            impact=spec.impact,
            severity=spec.severity,
            fields=list(spec.fields),
            declared_clause_ref=spec.clause_ref,
        )
        if spec.clause_ref:
            rule.clause_link = RuleClauseLink(
                clause_ref=spec.clause_ref, document_id=source_document_id, method="MANUAL", confirmed=True
            )
        rule_set.rules.append(rule)
    db.add(rule_set)
    db.flush()
    return rule_set, False


def get_rule_set(db: Session, rule_set_id: uuid.UUID) -> RuleSet:
    rs = db.get(RuleSet, rule_set_id)
    if rs is None:
        raise NotFoundError(f"Rule set {rule_set_id} not found")
    return rs


def resolve_rule_sets(db: Session, ids: list[uuid.UUID]) -> list[RuleSet]:
    if ids:
        return [get_rule_set(db, i) for i in ids]
    sets = list(db.scalars(select(RuleSet).where(RuleSet.status == "ACTIVE").order_by(RuleSet.regulator)))
    if not sets:
        raise ValidationFailedError("No ACTIVE rule sets. Upload a rules JSON first.", code="NO_RULES")
    return sets


def _citation(link: RuleClauseLink | None) -> str | None:
    if link is None or not link.citation_label:
        return None
    # Auto-suggested links are labelled until a reviewer confirms them (interpretability / human oversight).
    return link.citation_label if link.confirmed else f"{link.citation_label} — suggested source, unconfirmed"


def to_specs(rule_sets: list[RuleSet]) -> list[RuleSpec]:
    specs = []
    for rs in rule_sets:
        for r in rs.rules:
            if not r.enabled:
                continue
            link = r.clause_link
            specs.append(
                RuleSpec(
                    code=r.code,
                    regulator=rs.regulator,
                    description=r.description,
                    logic=r.logic,
                    impact=r.impact,
                    severity=r.severity,
                    applies_when=r.applies_when,
                    fields=tuple(r.fields),
                    clause_ref=(link.clause_ref if link else None) or r.declared_clause_ref,
                    citation=_citation(link),
                    rule_id=str(r.id),
                )
            )
    return specs
