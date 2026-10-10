"""Test harness: SQLite DB + temp storage + in-process publisher (no Redis/Postgres needed)."""

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="iris-ingestion-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("STORAGE_DIR", f"{_TMP}/files")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_JSON", "false")

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_publisher, get_storage
from app.db import get_engine, get_sessionmaker
from app.main import app
from app.models import Base
from app.services.processing import process_version
from iris_common.events import Tasks

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "data" / "sample_input" / "regulations"


class InlinePublisher:
    """Runs ingestion's own tasks synchronously; records tasks addressed to other services."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, task_name: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.sent.append((task_name, kwargs))
        if task_name == Tasks.PROCESS_VERSION:
            import uuid

            with get_sessionmaker()() as db:
                process_version(db, uuid.UUID(kwargs["version_id"]), get_storage(), self)


@pytest.fixture(autouse=True)
def _fresh_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def publisher() -> InlinePublisher:
    return InlinePublisher()


@pytest.fixture
def client(publisher: InlinePublisher):
    app.dependency_overrides[get_publisher] = lambda: publisher
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def sample(name: str) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()
