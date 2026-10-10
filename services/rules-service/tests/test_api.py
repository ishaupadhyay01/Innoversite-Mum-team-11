"""Rules-service API tests (FastAPI TestClient + SQLite). Skipped without FastAPI/SQLAlchemy."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

_TMP = Path(tempfile.mkdtemp(prefix="iris-rules-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SEARCH_URL"] = "http://127.0.0.1:9"  # nothing listens: related-text lookup reports 'unavailable'

from fastapi.testclient import TestClient  # noqa: E402

from iris_shared.db import get_engine  # noqa: E402
from iris_shared.models import Base  # noqa: E402


@pytest.fixture(scope="module")
def client():  # type: ignore[no-untyped-def]
    Base.metadata.create_all(get_engine())
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def analysis(client: TestClient) -> dict:
    r = client.post("/api/impact-matrix", json={"include_related_text": False})
    assert r.status_code == 201, r.text
    return r.json()


def test_rules_listing(client: TestClient) -> None:
    data = client.get("/api/rules").json()
    assert data["total_rules"] == 8 and data["valid_rules"] == 8
    assert data["regulators"] == ["EMIR", "FCA", "MiFID II"]
    assert "schema: non-standard key '$$schema' treated as '$schema'" in data["schema"]["normalization_notes"]


def test_impact_matrix_run_and_filters(client: TestClient, analysis: dict) -> None:
    assert analysis["status"] == "completed"
    assert analysis["summary"]["status_counts"]["FAIL"] == 209
    page = client.get(f"/api/impact-matrix/{analysis['id']}", params={"status": "FAIL", "rule_id": "MIFID-2", "page_size": 50}).json()
    assert page["total"] == 8
    assert {row["trade_id"] for row in page["items"]} >= {"T000004"}
    sorted_page = client.get(
        f"/api/impact-matrix/{analysis['id']}", params={"status": "FAIL", "sort_by": "trade_id", "sort_dir": "desc"}
    ).json()
    ids = [r["trade_id"] for r in sorted_page["items"]]
    assert ids == sorted(ids, reverse=True)


def test_result_detail_contains_trade_rule_and_honest_citation(client: TestClient, analysis: dict) -> None:
    page = client.get(f"/api/impact-matrix/{analysis['id']}", params={"trade_id": "T000004", "rule_id": "MIFID-2"}).json()
    row = page["items"][0]
    detail = client.get(f"/api/impact-matrix/{analysis['id']}/results/{row['id']}").json()
    assert detail["trade"]["Price"] == -99.9
    assert detail["rule"]["id"] == "MIFID-2" and detail["rule"]["citation"] is None
    assert detail["result"]["rule_source"] == "rules_mifid.json#MIFID-2"


def test_csv_export_matches_backend_rows(client: TestClient, analysis: dict) -> None:
    r = client.get(f"/api/impact-matrix/{analysis['id']}/export", params={"status": "FAIL"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 209
    assert {row["Status"] for row in rows} == {"FAIL"}


def test_request_validation_errors(client: TestClient, analysis: dict) -> None:
    r = client.get(f"/api/impact-matrix/{analysis['id']}", params={"status": "MAYBE"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_status"
    r = client.post("/api/impact-matrix", json={"dataset": "nope.csv"})
    assert r.status_code == 404
    r = client.post("/api/impact-matrix", json={"regulators": ["NOBODY"]})
    assert r.status_code == 422
    r = client.get(f"/api/impact-matrix/{analysis['id']}", params={"page_size": 5000})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_checklist_gap_and_trade_query(client: TestClient) -> None:
    cl = client.get("/api/checklist", params={"trade_id": "T000004"}).json()
    assert {i["rule_id"]: i["status"] for i in cl["items"]}["MIFID-2"] == "FAIL"
    assert client.get("/api/checklist", params={"trade_id": "NOPE"}).status_code == 404
    gap = client.post("/api/gap-analysis", json={"regulators": ["MiFID II"]}).json()
    assert gap["schema_findings"]["enabled"] is True
    q = client.post("/api/trades/query", json={"question": "Which trades are missing a Counterparty LEI?"}).json()
    assert q["matched"] and q["count"] == 18


def test_validate_endpoint(client: TestClient) -> None:
    bad = client.post("/api/rules/validate", json={"regulator": "X", "rules": [{"id": "X-1", "logic": {"nope": []}}]}).json()
    assert bad["valid"] is False
    good = client.post(
        "/api/rules/validate", json={"regulator": "X", "rules": [{"id": "X-1", "description": "d", "logic": {">": [{"var": "Price"}, 0]}}]}
    ).json()
    assert good["valid"] is True


def test_trade_verdicts_combine_selected_rules_with_and(client: TestClient, analysis: dict) -> None:
    assert analysis["summary"]["combined"]["compliant_trades"] == 44
    data = client.get(f"/api/impact-matrix/{analysis['id']}/trades", params={"overall": "FAIL", "page_size": 200}).json()
    assert data["combined"]["non_compliant_trades"] == 156 and data["total"] == 156
    t4 = next(v for v in data["items"] if v["trade_id"] == "T000004")
    assert t4["failed_rule_ids"] == ["FCA-2", "MIFID-2"]
    one = client.get(f"/api/impact-matrix/{analysis['id']}/trades", params={"trade_id": "T000008"}).json()
    assert one["total"] == 1 and one["items"][0]["overall"] == "PASS"
    assert client.get(f"/api/impact-matrix/{analysis['id']}/trades", params={"overall": "BAD"}).status_code == 422

    subset = client.post("/api/impact-matrix", json={"rule_ids": ["EMIR-1", "EMIR-2", "FCA-1"], "include_related_text": False}).json()
    assert subset["summary"]["combined"]["expression"] == "EMIR-1 AND EMIR-2 AND FCA-1"
    assert subset["summary"]["combined"]["status_counts"]["FAIL"] == 21

    r = client.get(f"/api/impact-matrix/{analysis['id']}/export/trades", params={"overall": "FAIL"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:3] == ["Trade_ID", "Asset_Class", "Overall_Status"] and len(rows) == 157
