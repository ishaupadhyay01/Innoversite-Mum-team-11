from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_actor, get_publisher
from app.models import ValidationRun
from app.publisher import EventPublisher
from app.schemas import MatrixPage, ResultRow, RunCreate, RunOut, RunStats
from app.services import matrix
from app.services.runs import create_run, get_run
from iris_common.events import Tasks
from iris_common.pagination import Page, PageParams

router = APIRouter(prefix="/api/v1/runs", tags=["impact analysis"])


@router.post(
    "",
    response_model=RunOut,
    status_code=202,
    summary="Start an impact analysis: evaluate a trade dataset against rule sets (async)",
)
def start_run(
    body: RunCreate,
    db: Session = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
    settings: Settings = Depends(get_settings),
    actor: str | None = Depends(get_actor),
) -> RunOut:
    run = create_run(db, settings, body.dataset_id, body.rule_set_ids, body.document_version_id, actor)
    db.commit()
    publisher.send(Tasks.EXECUTE_RUN, run_id=str(run.id))
    db.refresh(run)
    return RunOut.model_validate(run)


@router.get("", response_model=list[RunOut])
def list_runs(limit: int = Query(50, le=200), db: Session = Depends(get_db)) -> list[RunOut]:
    return [
        RunOut.model_validate(r)
        for r in db.scalars(select(ValidationRun).order_by(ValidationRun.created_at.desc()).limit(limit))
    ]


@router.get("/{run_id}", response_model=RunOut, summary="Run status & progress (poll until COMPLETED)")
def get(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunOut:
    return RunOut.model_validate(get_run(db, run_id))


@router.get("/{run_id}/stats", response_model=RunStats, summary="Compliance statistics")
def stats(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunStats:
    return matrix.stats(db, run_id)


def _filters(
    status: list[Literal["PASS", "FAIL", "NOT_APPLICABLE", "ERROR"]] = Query([]),
    rule_code: list[str] = Query([]),
    regulator: list[str] = Query([]),
    severity: list[str] = Query([]),
    asset_class: list[str] = Query([]),
    trade_id: str | None = None,
    q: str | None = Query(None, description="Search within explanations"),
) -> dict:
    return dict(
        status=list(status),
        rule_code=rule_code,
        regulator=regulator,
        severity=severity,
        asset_class=asset_class,
        trade_id=trade_id,
        q=q,
    )


@router.get(
    "/{run_id}/results",
    response_model=Page[ResultRow],
    summary="Impact Matrix (flat): one row per trade × rule, filterable, sortable, paginated",
)
def results(
    run_id: uuid.UUID,
    filters: dict = Depends(_filters),
    params: PageParams = Depends(),
    sort: str = "row_number",
    desc: bool = False,
    db: Session = Depends(get_db),
) -> Page[ResultRow]:
    get_run(db, run_id)
    rows, total = matrix.page_results(db, matrix.filtered(run_id, **filters), sort, desc, params.offset, params.size)
    return Page.build([ResultRow.model_validate(r) for r in rows], total, params)


@router.get(
    "/{run_id}/matrix", response_model=MatrixPage, summary="Impact Matrix (pivot): trades as rows, rules as columns"
)
def pivot(
    run_id: uuid.UUID, only_failing: bool = False, params: PageParams = Depends(), db: Session = Depends(get_db)
) -> MatrixPage:
    return matrix.pivot(
        db, get_run(db, run_id), only_failing=only_failing, offset=params.offset, size=params.size, page=params.page
    )


@router.get("/{run_id}/export.csv", response_class=StreamingResponse, summary="Download the Impact Matrix as CSV")
def export(run_id: uuid.UUID, filters: dict = Depends(_filters), db: Session = Depends(get_db)) -> StreamingResponse:
    get_run(db, run_id)
    return StreamingResponse(
        matrix.export_csv(db, matrix.filtered(run_id, **filters)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="impact-matrix-{run_id}.csv"'},
    )
