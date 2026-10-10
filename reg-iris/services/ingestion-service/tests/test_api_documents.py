from iris_common.events import Tasks
from tests.conftest import sample


def _upload(client, name, regulator="MiFID II", **form):
    return client.post(
        "/api/v1/documents",
        files={"file": (name, sample(name))},
        data={"regulator": regulator, "jurisdiction": "EU", **form},
    )


def test_upload_processes_activates_and_notifies_search(client, publisher):
    resp = _upload(client, "MiFID_II_2023_v1.pdf", title="MiFID II Trade Reporting", effective_date="2023-07-01")
    assert resp.status_code == 202, resp.text
    version_id = resp.json()["version"]["id"]

    version = client.get(f"/api/v1/versions/{version_id}").json()
    assert version["processing_status"] == "READY"
    assert version["status"] == "ACTIVE"
    assert version["clause_count"] == 6
    assert (
        Tasks.INDEX_VERSION,
        {"version_id": version_id, "document_id": version["document_id"], "status": "ACTIVE"},
    ) in publisher.sent

    cards = client.get("/api/v1/whats-new").json()
    assert cards["total"] == 1 and cards["items"][0]["card_type"] == "NEW_DOCUMENT"


def test_exact_duplicate_is_rejected_with_reference(client):
    first = _upload(client, "EMIR_2021_v1.pdf", regulator="EMIR").json()
    again = _upload(client, "EMIR_2021_v1.pdf", regulator="EMIR")
    assert again.status_code == 409
    err = again.json()["error"]
    assert err["code"] == "DUPLICATE_DOCUMENT"
    assert err["details"]["version_id"] == first["version"]["id"]


def test_new_version_flips_active_and_generates_diff_card(client):
    v1 = _upload(client, "MiFID_II_2023_v1.pdf", title="MiFID II Trade Reporting").json()
    doc_id = v1["document"]["id"]
    v2 = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("MiFID_II_2023_v2.pdf", sample("MiFID_II_2023_v2.pdf"))},
        data={"version_label": "v2.0"},
    ).json()

    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    statuses = {v["version_label"]: v["status"] for v in detail["versions"]}
    assert statuses == {"v1.0": "INACTIVE", "v2.0": "ACTIVE"}
    assert detail["active_version_id"] == v2["version"]["id"]

    card = client.get("/api/v1/whats-new").json()["items"][0]
    assert card["card_type"] == "NEW_VERSION"
    assert card["summary"]["ADDED"] == 1  # Paragraph 7: Execution Venue Disclosure
    assert "Paragraph 7" in card["headline"]

    diff = client.get(f"/api/v1/versions/{v2['version']['id']}/diff").json()
    assert {c["clause_ref"] for c in diff["changes"] if c["change"] == "ADDED"} == {"Paragraph 7"}

    alerts = client.get("/api/v1/alerts?unread_only=true").json()
    assert len(alerts) == 2


def test_rollback_by_reactivating_old_version(client):
    v1 = _upload(client, "SEC_GUIDANCE_2023_v1.pdf", regulator="SEC").json()
    doc_id = v1["document"]["id"]
    client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("SEC_GUIDANCE_2023_v2.pdf", sample("SEC_GUIDANCE_2023_v2.pdf"))},
    )
    resp = client.post(f"/api/v1/versions/{v1['version']['id']}/activate")
    assert resp.status_code == 200 and resp.json()["status"] == "ACTIVE"
    actives = [v for v in client.get(f"/api/v1/documents/{doc_id}/versions").json() if v["status"] == "ACTIVE"]
    assert len(actives) == 1


def test_match_suggestions_recommend_new_version(client):
    _upload(client, "EMIR_2021_v1.pdf", regulator="EMIR", title="EMIR Trade Reporting")
    _upload(client, "Dodd_Frank_2022.pdf", regulator="Dodd‑Frank")
    resp = client.post(
        "/api/v1/documents/match-suggestions",
        files={"file": ("EMIR_2021_v2.pdf", sample("EMIR_2021_v2.pdf"))},
        data={"regulator": "EMIR"},
    )
    body = resp.json()
    assert body["recommendation"] == "NEW_VERSION"
    assert body["candidates"][0]["title"] == "EMIR Trade Reporting"


def test_invalid_file_is_rejected(client):
    resp = client.post("/api/v1/documents", files={"file": ("x.pdf", b"not a pdf")}, data={"regulator": "FCA"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_internal_index_payload(client):
    v = _upload(client, "FCA_Guidance_2023.html", regulator="FCA", jurisdiction="UK").json()
    payload = client.get(f"/internal/v1/versions/{v['version']['id']}/index-payload").json()
    assert payload["regulator"] == "FCA" and len(payload["clauses"]) == 7
