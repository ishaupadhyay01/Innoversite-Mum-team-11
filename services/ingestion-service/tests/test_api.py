"""API + pipeline tests with SQLite and an in-memory fake of the search service.

Requires FastAPI and SQLAlchemy (installed in Docker / CI). Skipped otherwise.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

_TMP = Path(tempfile.mkdtemp(prefix="iris-ingestion-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.services import search_client  # noqa: E402
from iris_shared.db import get_engine, session_scope  # noqa: E402
from iris_shared.models import Base, DocumentVersion, RegulatoryAlert  # noqa: E402

REGULATIONS = Path(__file__).resolve().parents[3] / "data" / "regulations"


class FakeIndex:
    """Stands in for the search service: stores paragraphs per version."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def index_version(self, meta: dict[str, Any], paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
        vid = meta["document_version_id"]
        self.docs = {k: v for k, v in self.docs.items() if v["document_version_id"] != vid}
        for p in paragraphs:
            self.docs[p["paragraph_id"]] = dict(p)
        return {"indexed": len(paragraphs), "errors": []}

    def set_latest(self, document_id: int, version_id: int) -> dict[str, int]:
        for d in self.docs.values():
            if d["document_id"] == str(document_id):
                d["is_latest"] = d["document_version_id"] == str(version_id)
        return {"updated": 1}

    def count(self, version_id: int) -> int:
        return sum(1 for d in self.docs.values() if d["document_version_id"] == str(version_id))


@pytest.fixture(scope="module")
def fake_index() -> FakeIndex:
    return FakeIndex()


@pytest.fixture(scope="module")
def client(fake_index: FakeIndex):  # type: ignore[no-untyped-def]
    mp = pytest.MonkeyPatch()
    mp.setattr(search_client, "is_ready", lambda: True)
    mp.setattr(search_client, "index_version", fake_index.index_version)
    mp.setattr(search_client, "set_latest", fake_index.set_latest)
    mp.setattr(search_client, "version_paragraph_count", fake_index.count)
    mp.setattr(search_client, "reset_index", lambda: None)
    mp.setattr(search_client, "reconcile", lambda ids: {"deleted": 0})
    Base.metadata.create_all(get_engine())
    from app.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def _seed() -> None:
    from app.services.seeding import run_seed

    assert run_seed() is not None


def test_initial_import_indexes_dataset_with_historical_alerts(client: TestClient, fake_index: FakeIndex) -> None:
    _seed()
    with session_scope() as s:
        versions = s.scalars(select(DocumentVersion)).all()
        assert len(versions) == 10
        assert all(v.status == "indexed" for v in versions)
        alerts = s.scalars(select(RegulatoryAlert)).all()
        assert len(alerts) == 10
        assert all(a.is_read and a.source == "initial_import" for a in alerts)
        mifid_v2 = next(a for a in alerts if a.document_name == "MiFID_II_2023_v2.pdf")
        assert mifid_v2.change_types == ["New Version", "Added Clause"]
        assert mifid_v2.event_time.year == 2024  # historical timestamp, not "today"
    latest = [d for d in fake_index.docs.values() if d["document_name"] == "MiFID_II_2023_v2.pdf"]
    assert latest and all(d["is_latest"] for d in latest)
    old = [d for d in fake_index.docs.values() if d["document_name"] == "MiFID_II_2023_v1.pdf"]
    assert old and not any(d["is_latest"] for d in old)


def test_repeated_import_does_not_duplicate(client: TestClient) -> None:
    _seed()
    with session_scope() as s:
        assert s.scalar(select(func.count(DocumentVersion.id))) == 10
        assert s.scalar(select(func.count(RegulatoryAlert.id))) == 10
    run = client.get("/api/imports/latest").json()
    assert run["files_skipped"] == 10 and run["files_failed"] == 0


def test_document_listing_and_versions(client: TestClient) -> None:
    page = client.get("/api/documents", params={"regulator": "MiFID II"}).json()
    assert page["total"] == 1
    doc = page["items"][0]
    assert doc["version_count"] == 2
    assert doc["latest_version"]["version_label"] == "v2.0"
    versions = client.get(f"/api/documents/{doc['id']}/versions").json()
    assert [v["version_label"] for v in versions] == ["v1.0", "v2.0"]


def test_compare_endpoint_reports_real_difference(client: TestClient) -> None:
    doc = client.get("/api/documents", params={"q": "SEC"}).json()["items"][0]
    v = client.get(f"/api/documents/{doc['id']}/versions").json()
    diff = client.get("/api/documents/compare", params={"base_version_id": v[0]["id"], "target_version_id": v[1]["id"]}).json()
    assert diff["stats"]["added"] == 1
    assert "Swap Identifier" in diff["summary"]


def test_source_endpoint_serves_original_pdf(client: TestClient) -> None:
    doc = client.get("/api/documents", params={"q": "Dodd"}).json()["items"][0]
    r = client.get(f"/api/documents/{doc['id']}/source")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == (REGULATIONS / "Dodd_Frank_2022.pdf").read_bytes()


def test_upload_new_version_creates_unread_alert(client: TestClient, tmp_path: Path) -> None:
    doc = client.get("/api/documents", params={"regulator": "CFTC"}).json()["items"][0]
    text = (REGULATIONS / "CFTC_2022.txt").read_text(encoding="utf-8")
    text += "\r\n\r\nQ11: Is a new field required from 2025?\r\nA11: Yes - the Execution_Venue field becomes mandatory.\r\n"
    r = client.post(
        "/api/documents/upload",
        files={"file": ("CFTC_2022_v2.txt", text.encode("utf-8"), "text/plain")},
        data={"document_id": str(doc["id"]), "version_label": "v2.0"},
    )
    assert r.status_code == 202, r.text
    job = client.get(r.json()["status_url"]).json()
    assert job["status"] == "indexed", job
    alerts = client.get("/api/alerts", params={"unread_only": True}).json()
    assert alerts["unread"] == 1
    alert = alerts["items"][0]
    assert alert["change_types"] == ["New Version", "Added Clause"]
    assert alert["previous_version_label"] == "v1.0" and alert["new_version_label"] == "v2.0"
    # mark read
    updated = client.patch(f"/api/alerts/{alert['id']}/read", json={"is_read": True}).json()
    assert updated["is_read"] is True


def test_upload_validation_errors(client: TestClient) -> None:
    r = client.post("/api/documents/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data={"regulator": "X"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_type"
    r = client.post("/api/documents/upload", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "regulator_required"
    dup = (REGULATIONS / "MiFID_II_2023_v1.pdf").read_bytes()
    r = client.post("/api/documents/upload", files={"file": ("copy.pdf", dup, "application/pdf")}, data={"regulator": "MiFID II"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_document"


def test_unknown_document_is_404_with_error_envelope(client: TestClient) -> None:
    r = client.get("/api/documents/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "document_not_found"
