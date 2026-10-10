"""'What's New' alerts: persisted notifications created by document ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from iris_shared import audit
from iris_shared.db import get_session
from iris_shared.models import RegulatoryAlert
from iris_shared.web import ApiError

from ..schemas import AlertOut, AlertPage, AlertReadUpdate

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


def _unread(session: Session) -> int:
    return session.scalar(select(func.count(RegulatoryAlert.id)).where(RegulatoryAlert.is_read.is_(False))) or 0


@router.get("", response_model=AlertPage, summary="List alerts (newest first) with unread count")
def list_alerts(
    unread_only: bool = False,
    q: str | None = Query(None, max_length=200, description="Search title, summary, document or regulator"),
    regulator: list[str] = Query(default=[]),
    change_type: str | None = Query(None, description="New Document | New Version | Added Clause | Removed Clause | Modified Clause"),
    source: str | None = Query(None, pattern="^(initial_import|upload)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> AlertPage:
    stmt = select(RegulatoryAlert)
    if unread_only:
        stmt = stmt.where(RegulatoryAlert.is_read.is_(False))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                RegulatoryAlert.title.ilike(like),
                RegulatoryAlert.summary.ilike(like),
                RegulatoryAlert.document_name.ilike(like),
                RegulatoryAlert.regulator.ilike(like),
            )
        )
    if regulator:
        stmt = stmt.where(RegulatoryAlert.regulator.in_(regulator))
    if source:
        stmt = stmt.where(RegulatoryAlert.source == source)
    rows = session.scalars(stmt.order_by(RegulatoryAlert.event_time.desc(), RegulatoryAlert.id.desc())).all()
    if change_type:
        rows = [a for a in rows if change_type in (a.change_types or [])]
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return AlertPage(
        items=[AlertOut.model_validate(a) for a in page_rows],
        total=total,
        unread=_unread(session),
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", summary="Unread alert counter (polled by the UI)")
def unread_count(session: Session = Depends(get_session)) -> dict[str, int | None]:
    latest_id = session.scalar(select(func.max(RegulatoryAlert.id)))
    return {"unread": _unread(session), "latest_id": latest_id}


@router.post("/read-all", summary="Mark all alerts as read")
def read_all(session: Session = Depends(get_session)) -> dict[str, int]:
    result = session.execute(update(RegulatoryAlert).where(RegulatoryAlert.is_read.is_(False)).values(is_read=True))
    audit.record(session, "ingestion", "alert.read_all", f"Marked {result.rowcount} alert(s) read")
    session.commit()
    return {"updated": result.rowcount or 0}


@router.get("/{alert_id}", response_model=AlertOut, summary="Alert detail")
def get_alert(alert_id: int, session: Session = Depends(get_session)) -> AlertOut:
    alert = session.get(RegulatoryAlert, alert_id)
    if alert is None:
        raise ApiError(404, "alert_not_found", f"Alert {alert_id} not found")
    return AlertOut.model_validate(alert)


@router.patch("/{alert_id}/read", response_model=AlertOut, summary="Mark an alert read or unread")
def mark_read(alert_id: int, body: AlertReadUpdate | None = None, session: Session = Depends(get_session)) -> AlertOut:
    alert = session.get(RegulatoryAlert, alert_id)
    if alert is None:
        raise ApiError(404, "alert_not_found", f"Alert {alert_id} not found")
    alert.is_read = body.is_read if body else True
    audit.record(
        session,
        "ingestion",
        "alert.read" if alert.is_read else "alert.unread",
        f"Alert {alert_id} marked {'read' if alert.is_read else 'unread'}",
        "alert",
        alert_id,
    )
    session.commit()
    session.refresh(alert)
    return AlertOut.model_validate(alert)
