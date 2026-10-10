import os
import tempfile
import uuid
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="iris-rules-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("STORAGE_DIR", f"{_TMP}/files")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("CHUNK_SIZE", "64")  # force several chunks on the 200-row sample

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.deps import get_publisher, get_schema, get_storage
from app.main import app
from app.models import Base
from app.services.runs import execute_run_inline
from iris_common.events import Tasks

DATA = Path(__file__).resolve().parents[3] / "data" / "sample_input"
FIELDS = {
    "Trade_ID",
    "Asset_Class",
    "Timestamp",
    "Counterparty_LEI",
    "Price",
    "Quantity",
    "Currency",
    "Maturity_Date",
    "Underlying_ISIN",
}


class InlinePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, task_name: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.sent.append((task_name, kwargs))
        if task_name == Tasks.EXECUTE_RUN:
            with get_sessionmaker()() as db:
                execute_run_inline(db, uuid.UUID(kwargs["run_id"]), get_storage(), get_schema(), get_settings())


@pytest.fixture
def publisher() -> InlinePublisher:
    return InlinePublisher()


@pytest.fixture
def client(publisher):
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_publisher] = lambda: publisher
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
