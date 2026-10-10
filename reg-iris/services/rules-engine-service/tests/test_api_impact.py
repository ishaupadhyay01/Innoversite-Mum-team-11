import csv
import io

from tests.conftest import DATA


def _upload_all(client):
    for name in ("rules_mifid.json", "rules_emir.json", "rules_fca.json"):
        r = client.post("/api/v1/rule-sets", files={"file": (name, (DATA / "rules" / name).read_bytes())})
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/datasets", files={"file": ("sample_trades.csv", (DATA / "trades" / "sample_trades.csv").read_bytes())}
    )
    assert r.status_code == 201, r.text
    return r.json()["dataset"]


def test_end_to_end_impact_matrix(client):
    ds = _upload_all(client)
    assert ds["row_count"] == 200 and ds["status"] == "VALID_WITH_WARNINGS"

    run = client.post("/api/v1/runs", json={"dataset_id": ds["id"]}).json()
    run = client.get(f"/api/v1/runs/{run['id']}").json()
    assert run["status"] == "COMPLETED" and run["chunks_done"] == run["chunks_total"] == 4

    stats = client.get(f"/api/v1/runs/{run['id']}/stats").json()
    assert stats["total_checks"] == 200 * 8
    by_rule = {r["rule_code"]: r for r in stats["by_rule"]}
    assert by_rule["MIFID-2"]["failed"] == 8  # negative prices
    assert by_rule["FCA-1"]["failed"] == 9  # currency XYZ
    assert by_rule["MIFID-4"]["failed"] == 1  # pre-2018 trade
    assert stats["passed"] > 0 and stats["failed"] > 0  # both PASS and FAIL are reported

    page = client.get(
        f"/api/v1/runs/{run['id']}/results", params={"status": "FAIL", "rule_code": "MIFID-2", "size": 5}
    ).json()
    assert page["total"] == 8 and len(page["items"]) == 5 and page["pages"] == 2
    assert page["items"][0]["explanation"].startswith("Price (")

    pivot = client.get(f"/api/v1/runs/{run['id']}/matrix", params={"size": 10, "only_failing": True}).json()
    assert len(pivot["columns"]) == 8 and all(r["fail_count"] > 0 for r in pivot["rows"])

    exported = client.get(f"/api/v1/runs/{run['id']}/export.csv", params={"status": "FAIL"})
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert exported.headers["content-type"].startswith("text/csv")
    assert len(rows) == stats["failed"] and {"Trade_ID", "Rule_ID", "Explanation"} <= rows[0].keys()


def test_reupload_is_idempotent_and_new_version_replaces_active(client):
    body = (DATA / "rules" / "rules_fca.json").read_bytes()
    first = client.post("/api/v1/rule-sets", files={"file": ("f.json", body)}).json()
    again = client.post("/api/v1/rule-sets", files={"file": ("f.json", body)}).json()
    assert again["already_uploaded"] and again["rule_set"]["id"] == first["rule_set"]["id"]
    v2 = client.post("/api/v1/rule-sets", files={"file": ("f2.json", body.replace(b'"CHF"]', b'"CHF","CAD"]'))})
    assert v2.json()["rule_set"]["version_number"] == 2
    active = client.get("/api/v1/rule-sets", params={"regulator": "FCA"}).json()
    assert [r["version_number"] for r in active] == [2]


def test_invalid_csv_is_rejected_for_analysis(client):
    client.post("/api/v1/rule-sets", files={"file": ("m.json", (DATA / "rules" / "rules_mifid.json").read_bytes())})
    ds = client.post("/api/v1/datasets", files={"file": ("bad.csv", b"Trade_ID,Price\nT1,5\n")}).json()["dataset"]
    assert ds["status"] == "INVALID" and "Missing required column" in ds["validation"]["errors"][0]
    resp = client.post("/api/v1/runs", json={"dataset_id": ds["id"]})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "DATASET_INVALID"


def test_single_trade_evaluation_endpoint(client):
    client.post("/api/v1/rule-sets", files={"file": ("m.json", (DATA / "rules" / "rules_mifid.json").read_bytes())})
    resp = client.post(
        "/api/v1/evaluate",
        json={"trade": {"Trade_ID": "X1", "Asset_Class": "Bond", "Price": "-1", "Timestamp": "2024-01-01T00:00:00Z"}},
    ).json()
    assert resp["compliant"] is False
    statuses = {o["rule_code"]: o["status"] for o in resp["outcomes"]}
    assert statuses["MIFID-2"] == "FAIL" and statuses["MIFID-3"] == "NOT_APPLICABLE"


def test_rule_file_dry_run_validation(client):
    resp = client.post(
        "/api/v1/rule-sets/validate", files={"file": ("e.json", (DATA / "rules" / "rules_emir.json").read_bytes())}
    )
    body = resp.json()
    assert body["valid"] is True and any(i["level"] == "WARNING" for i in body["issues"])
