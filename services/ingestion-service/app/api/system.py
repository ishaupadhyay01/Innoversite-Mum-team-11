"""Import status, audit trail and health endpoints."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from iris_shared.config import get_settings
from iris_shared.db import check_database, get_session
from iris_shared.models import AuditEvent, ImportRun

from ..schemas import AuditOut, ImportRunOut
from ..services import search_client
from ..services.seeding import run_seed

router = APIRouter(tags=["System"])


@router.get("/health", summary="Service health with dependency checks")
def health() -> dict[str, object]:
    db_ok, db_detail = check_database()
    settings = get_settings()
    search_ok = search_client.is_ready()
    return {
        "service": "ingestion",
        "status": "ok" if db_ok else "degraded",
        "checks": {
            "database": {"ok": db_ok, "detail": db_detail},
            "search_service": {"ok": search_ok, "detail": "reachable" if search_ok else "not reachable / Elasticsearch not ready"},
            "dataset_dir": {"ok": settings.regulations_dir.exists(), "detail": str(settings.regulations_dir)},
            "upload_dir": {"ok": settings.upload_dir.exists(), "detail": str(settings.upload_dir)},
        },
    }


@router.get("/api/imports/latest", response_model=ImportRunOut | None, tags=["Imports"], summary="Latest dataset import run")
def latest_import(session: Session = Depends(get_session)) -> ImportRunOut | None:
    run = session.scalar(select(ImportRun).order_by(ImportRun.id.desc()).limit(1))
    return ImportRunOut.model_validate(run) if run else None


@router.post("/api/imports/run", status_code=status.HTTP_202_ACCEPTED, tags=["Imports"], summary="Re-run the idempotent dataset import")
def trigger_import() -> dict[str, str]:
    threading.Thread(target=run_seed, name="dataset-import-manual", daemon=True).start()
    return {"status": "started", "status_url": "/api/imports/latest"}


@router.get("/api/audit", response_model=list[AuditOut], tags=["Audit"], summary="Recent audit events from all services")
def audit_events(
    limit: int = Query(20, ge=1, le=200),
    action: str | None = Query(None, max_length=60),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    return [AuditOut.model_validate(e) for e in session.scalars(stmt).all()]
