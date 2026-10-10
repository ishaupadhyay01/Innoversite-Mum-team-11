"""Synchronous single-trade evaluation — lets existing trade-flow pipelines call the engine inline."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_schema
from app.engine import Status, evaluate_trade
from app.schemas import EvaluateRequest, EvaluateResponse, OutcomeOut
from app.services.rulesets import resolve_rule_sets, to_specs
from app.trades.reader import _coerce
from app.trades.schema import ReportingSchema

router = APIRouter(prefix="/api/v1", tags=["evaluate"])


@router.post("/evaluate", response_model=EvaluateResponse, summary="Evaluate ONE trade against rule sets now")
def evaluate(
    body: EvaluateRequest, db: Session = Depends(get_db), schema: ReportingSchema = Depends(get_schema)
) -> EvaluateResponse:
    types = {f.name: f.base_type for f in schema.fields}
    trade = {name: None for name in types}
    trade.update({k: _coerce(str(v), types.get(k, "string")) if v is not None else None for k, v in body.trade.items()})
    specs = to_specs(resolve_rule_sets(db, body.rule_set_ids))
    outcomes = evaluate_trade(trade, specs)
    return EvaluateResponse(
        trade_id=trade.get("Trade_ID"),
        compliant=not any(o.status is Status.FAIL for o in outcomes),
        outcomes=[
            OutcomeOut(
                rule_code=o.rule_code,
                regulator=s.regulator,
                status=o.status.value,
                explanation=o.explanation,
                field_values=o.field_values,
                citation_label=s.citation,
            )
            for s, o in zip(specs, outcomes, strict=True)
        ],
    )
