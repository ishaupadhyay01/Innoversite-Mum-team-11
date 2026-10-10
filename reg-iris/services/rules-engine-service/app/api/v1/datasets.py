from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_actor, get_schema, get_storage
from app.models import TradeDataset
from app.schemas import DatasetOut, DatasetUploadResult
from app.services.datasets import get_dataset, upload_dataset
from app.storage import FileStorage
from app.trades.schema import ReportingSchema

router = APIRouter(prefix="/api/v1", tags=["trade datasets"])


@router.post(
    "/datasets",
    response_model=DatasetUploadResult,
    status_code=201,
    summary="Upload a trade CSV; returns a validation report against the reporting schema",
)
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    schema: ReportingSchema = Depends(get_schema),
    actor: str | None = Depends(get_actor),
) -> DatasetUploadResult:
    ds, existed = upload_dataset(db, storage, settings, schema, file.filename or "trades.csv", await file.read(), actor)
    db.commit()
    return DatasetUploadResult(dataset=DatasetOut.model_validate(ds), already_uploaded=existed)


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)) -> list[DatasetOut]:
    return [
        DatasetOut.model_validate(d)
        for d in db.scalars(select(TradeDataset).order_by(TradeDataset.uploaded_at.desc()).limit(200))
    ]


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get(dataset_id: uuid.UUID, db: Session = Depends(get_db)) -> DatasetOut:
    return DatasetOut.model_validate(get_dataset(db, dataset_id))


@router.get("/schemas/trade-reporting", tags=["reference"], summary="The trade reporting schema in use")
def reporting_schema(schema: ReportingSchema = Depends(get_schema)) -> dict:
    return schema.raw
