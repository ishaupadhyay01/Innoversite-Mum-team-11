from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert, Document, WhatsNewCard
from app.schemas import AlertOut, WhatsNewCardOut
from app.services.diffing import require_card
from iris_common.errors import NotFoundError
from iris_common.pagination import Page, PageParams
from iris_common.text import canonical_regulator

router = APIRouter(prefix="/api/v1", tags=["whats-new & alerts"])


@router.get("/whats-new", response_model=Page[WhatsNewCardOut], summary="What's New cards, newest first")
def list_cards(
    params: PageParams = Depends(), regulator: str | None = None, db: Session = Depends(get_db)
) -> Page[WhatsNewCardOut]:
    stmt = select(WhatsNewCard)
    if regulator:
        stmt = stmt.join(Document, Document.id == WhatsNewCard.document_id).where(
            Document.regulator_canonical == canonical_regulator(regulator)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(WhatsNewCard.created_at.desc()).offset(params.offset).limit(params.size)).all()
    return Page.build([WhatsNewCardOut.model_validate(r) for r in rows], total, params)


@router.get("/whats-new/{card_id}", response_model=WhatsNewCardOut)
def get_card(card_id: uuid.UUID, db: Session = Depends(get_db)) -> WhatsNewCardOut:
    return WhatsNewCardOut.model_validate(require_card(db, card_id))


@router.get("/alerts", response_model=list[AlertOut], summary="Alert panel feed (poll every ~10s)")
def list_alerts(unread_only: bool = False, limit: int = 50, db: Session = Depends(get_db)) -> list[AlertOut]:
    stmt = select(Alert)
    if unread_only:
        stmt = stmt.where(Alert.read_at.is_(None))
    return [
        AlertOut.model_validate(a) for a in db.scalars(stmt.order_by(Alert.created_at.desc()).limit(min(limit, 200)))
    ]


@router.post("/alerts/{alert_id}/read", response_model=AlertOut)
def mark_read(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertOut:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    alert.read_at = alert.read_at or datetime.now(UTC)
    db.commit()
    return AlertOut.model_validate(alert)


@router.post("/alerts/read-all", status_code=204, response_class=Response, response_model=None)
def mark_all_read(db: Session = Depends(get_db)) -> None:
    db.execute(update(Alert).where(Alert.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    db.commit()
