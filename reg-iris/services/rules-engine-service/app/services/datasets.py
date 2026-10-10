from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import TradeDataset
from app.storage import FileStorage
from app.trades.schema import ReportingSchema
from app.trades.validation import validate_trade_csv
from iris_common.errors import NotFoundError, PayloadTooLargeError, ValidationFailedError
from iris_common.text import sha256_bytes


def upload_dataset(
    db: Session,
    storage: FileStorage,
    settings: Settings,
    schema: ReportingSchema,
    filename: str,
    data: bytes,
    actor: str | None,
) -> tuple[TradeDataset, bool]:
    if not filename.lower().endswith(".csv"):
        raise ValidationFailedError("Trade dataset must be a .csv file", code="UNSUPPORTED_FILE")
    if not data:
        raise ValidationFailedError("Uploaded file is empty", code="EMPTY_FILE")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File exceeds {settings.max_upload_mb} MB")
    sha = sha256_bytes(data)
    if existing := db.scalar(select(TradeDataset).where(TradeDataset.sha256 == sha)):
        return existing, True
    key = storage.save(data, sha, "csv")
    report = validate_trade_csv(storage.path(key), schema)
    ds = TradeDataset(
        filename=filename,
        storage_key=key,
        sha256=sha,
        file_size=len(data),
        row_count=report.row_count,
        status=report.status,
        validation=report.to_dict(),
        uploaded_by=actor,
    )
    db.add(ds)
    db.flush()
    return ds, False


def get_dataset(db: Session, dataset_id: uuid.UUID) -> TradeDataset:
    ds = db.get(TradeDataset, dataset_id)
    if ds is None:
        raise NotFoundError(f"Dataset {dataset_id} not found")
    return ds
