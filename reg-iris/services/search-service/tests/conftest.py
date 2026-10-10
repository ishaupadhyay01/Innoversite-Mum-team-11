"""Search tests run against the in-memory backend and a fake ingestion client."""

import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="iris-search-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("SEARCH_BACKEND", "memory")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_JSON", "false")

import pytest
from fastapi.testclient import TestClient

from app.backends.memory import InMemoryBackend
from app.backends.semantic import DisabledSemanticBackend
from app.db import get_engine
from app.deps import get_ingestion_client, get_keyword_backend, get_semantic_backend
from app.main import app
from app.models import Base

DOC = str(uuid.uuid4())
V1, V2 = str(uuid.uuid4()), str(uuid.uuid4())


def _payload(version_id: str, label: str, status: str, clauses: list[tuple[str, str, str, int]]) -> dict:
    return {
        "document_id": DOC,
        "version_id": version_id,
        "document_key": "mifid-ii",
        "title": "MiFID II Trade Reporting",
        "regulator": "MiFID II",
        "jurisdiction": "EU",
        "category": "Trade reporting",
        "version_label": label,
        "status": status,
        "effective_date": "2023-07-01",
        "file_name": f"MiFID_II_2023_{label}.pdf",
        "mime_type": "application/pdf",
        "clauses": [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, version_id + ref)),
                "ordinal": i,
                "clause_ref": ref,
                "title": title,
                "text": text,
                "page_start": page,
                "page_end": page,
                "anchor": None,
            }
            for i, (ref, title, text, page) in enumerate(clauses, 1)
        ],
    }


PAYLOADS = {
    V1: _payload(
        V1,
        "v1",
        "INACTIVE",
        [
            (
                "Paragraph 3",
                "Counterparty LEI Requirement",
                "The Counterparty_LEI must be a valid 20-character alphanumeric identifier.",
                1,
            ),
            ("Paragraph 5", "Timing of Reporting", "Report trades within one business day.", 1),
        ],
    ),
    V2: _payload(
        V2,
        "v2",
        "ACTIVE",
        [
            (
                "Paragraph 3",
                "Counterparty LEI Requirement",
                "The Counterparty_LEI must be a valid 20-character alphanumeric identifier issued by an accredited LOU.",
                1,
            ),
            ("Paragraph 7", "Execution Venue Disclosure", "Trades on MTFs must include the Execution_Venue MIC.", 2),
        ],
    ),
}


class FakeIngestion:
    def get(self, path: str):  # type: ignore[no-untyped-def]
        version_id = path.split("/")[4]
        return PAYLOADS[version_id]


@pytest.fixture
def backend() -> InMemoryBackend:
    return InMemoryBackend()


@pytest.fixture
def client(backend):
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_keyword_backend] = lambda: backend
    app.dependency_overrides[get_semantic_backend] = lambda: DisabledSemanticBackend()
    app.dependency_overrides[get_ingestion_client] = lambda: FakeIngestion()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
