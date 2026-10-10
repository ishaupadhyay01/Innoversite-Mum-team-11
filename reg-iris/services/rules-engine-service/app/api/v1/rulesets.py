from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_actor, get_publisher, get_schema
from app.models import Rule, RuleSet
from app.publisher import EventPublisher
from app.schemas import (
    ClauseLinkIn,
    RuleFileValidation,
    RuleOut,
    RuleSetDetail,
    RuleSetOut,
    RuleSetUploadResult,
)
from app.services.rulesets import get_rule_set, upload_rule_set, validate_rule_file
from app.services.traceability import set_manual_link
from app.trades.schema import ReportingSchema
from iris_common.errors import NotFoundError
from iris_common.events import Tasks

router = APIRouter(prefix="/api/v1", tags=["rule sets"])


@router.post(
    "/rule-sets/validate",
    response_model=RuleFileValidation,
    summary="Dry-run: validate + lint a rules JSON without storing it",
)
async def validate(file: UploadFile = File(...), schema: ReportingSchema = Depends(get_schema)) -> RuleFileValidation:
    ok, regulator, count, issues = validate_rule_file(await file.read(), schema)
    return RuleFileValidation(valid=ok, regulator=regulator, rule_count=count, issues=issues)


@router.post(
    "/rule-sets",
    response_model=RuleSetUploadResult,
    status_code=201,
    summary="Upload a rules JSON → becomes the ACTIVE rule set for its regulator",
)
async def upload(
    file: UploadFile = File(...),
    source_document_id: uuid.UUID | None = Form(None, description="Ingestion document these rules derive from"),
    db: Session = Depends(get_db),
    schema: ReportingSchema = Depends(get_schema),
    publisher: EventPublisher = Depends(get_publisher),
    settings: Settings = Depends(get_settings),
    actor: str | None = Depends(get_actor),
) -> RuleSetUploadResult:
    rule_set, existed = upload_rule_set(
        db, file.filename or "rules.json", await file.read(), schema, source_document_id=source_document_id, actor=actor
    )
    db.commit()
    if not existed and settings.auto_link_clauses:
        publisher.send(Tasks.LINK_RULE_CLAUSES, rule_set_id=str(rule_set.id))
    return RuleSetUploadResult(rule_set=RuleSetDetail.model_validate(rule_set), already_uploaded=existed)


@router.get("/rule-sets", response_model=list[RuleSetOut])
def list_rule_sets(
    status: str | None = "ACTIVE", regulator: str | None = None, db: Session = Depends(get_db)
) -> list[RuleSetOut]:
    stmt = select(RuleSet).order_by(RuleSet.regulator, RuleSet.version_number.desc())
    if status and status != "ALL":
        stmt = stmt.where(RuleSet.status == status)
    if regulator:
        stmt = stmt.where(RuleSet.regulator == regulator)
    return [RuleSetOut.model_validate(r) for r in db.scalars(stmt)]


@router.get("/rule-sets/{rule_set_id}", response_model=RuleSetDetail)
def get(rule_set_id: uuid.UUID, db: Session = Depends(get_db)) -> RuleSetDetail:
    return RuleSetDetail.model_validate(get_rule_set(db, rule_set_id))


@router.post(
    "/rule-sets/{rule_set_id}/link-clauses",
    status_code=202,
    tags=["traceability"],
    summary="(Re)run automatic rule → regulatory-clause linking via search-service",
)
def relink(
    rule_set_id: uuid.UUID, db: Session = Depends(get_db), publisher: EventPublisher = Depends(get_publisher)
) -> dict[str, str]:
    get_rule_set(db, rule_set_id)
    publisher.send(Tasks.LINK_RULE_CLAUSES, rule_set_id=str(rule_set_id))
    return {"status": "queued"}


@router.get("/rules/{rule_id}", response_model=RuleOut, tags=["traceability"])
def get_rule(rule_id: uuid.UUID, db: Session = Depends(get_db)) -> RuleOut:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise NotFoundError(f"Rule {rule_id} not found")
    return RuleOut.model_validate(rule)


@router.put(
    "/rules/{rule_id}/clause-link",
    response_model=RuleOut,
    tags=["traceability"],
    summary="Confirm/override which regulatory clause justifies this rule",
)
def put_clause_link(rule_id: uuid.UUID, body: ClauseLinkIn, db: Session = Depends(get_db)) -> RuleOut:
    return RuleOut.model_validate(set_manual_link(db, rule_id, body))
