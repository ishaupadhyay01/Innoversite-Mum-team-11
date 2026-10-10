from datetime import date

from app.backends.filters import es_filter_clauses
from app.schemas import SearchFilters
from tests.conftest import DOC, V1, V2


def _index_both(client):
    for v in (V1, V2):
        assert client.post(f"/api/v1/search/reindex/{v}").status_code == 200


def test_search_returns_clause_with_clickable_citation(client):
    _index_both(client)
    body = client.get("/api/v1/search", params={"q": "counterparty LEI"}).json()
    assert body["total"] == 1  # default status=ACTIVE hides v1
    hit = body["hits"][0]
    assert "<mark>" in hit["highlights"][0]
    cit = hit["citation"]
    assert cit["clause_ref"] == "Paragraph 3" and cit["page"] == 1
    assert cit["file_url"] == f"/api/v1/versions/{V2}/file#page=1"
    assert cit["label"].startswith("MiFID_II_2023_v2.pdf (v2), Paragraph 3")


def test_filters_by_regulator_status_and_date(client):
    _index_both(client)
    q = {"q": "LEI", "status": "ALL"}
    assert client.get("/api/v1/search", params={**q, "regulator": "Mifid ii"}).json()["total"] == 2
    assert client.get("/api/v1/search", params={**q, "regulator": "EMIR"}).json()["total"] == 0
    assert client.get("/api/v1/search", params={**q, "effective_from": "2024-01-01"}).json()["total"] == 0


def test_activation_change_updates_index_status(client, backend):
    _index_both(client)
    import uuid

    from app.backends.semantic import DisabledSemanticBackend
    from app.db import get_sessionmaker
    from app.services.indexer import apply_status_change

    with get_sessionmaker()() as db:
        apply_status_change(db, uuid.UUID(DOC), uuid.UUID(V1), backend, DisabledSemanticBackend())
    hit = client.get("/api/v1/search", params={"q": "LEI"}).json()["hits"][0]
    assert hit["citation"]["version_id"] == V1


def test_compare_highlights_added_removed_modified(client):
    resp = client.post("/api/v1/compare", json={"left_version_id": V1, "right_version_id": V2})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 0}
    modified = next(c for c in body["changes"] if c["change"] == "MODIFIED")
    assert any(op["op"] == "insert" and "accredited" in op["text"] for op in modified["inline"])
    assert client.get(f"/api/v1/compare/{body['id']}").status_code == 200


def test_semantic_mode_reports_disabled_cleanly(client):
    resp = client.get("/api/v1/search", params={"q": "LEI", "mode": "semantic"})
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "SEMANTIC_DISABLED"


def test_facets_list_filter_values(client):
    _index_both(client)
    facets = client.get("/api/v1/search/facets").json()
    assert facets["regulator"] == [{"value": "MiFID II", "count": 4}]


def test_es_filter_translation():
    f = SearchFilters(regulator=["Dodd‑Frank"], status="ACTIVE", effective_from=date(2022, 1, 1))
    clauses = es_filter_clauses(f)
    assert {"terms": {"regulator_canonical": ["DODD-FRANK"]}} in clauses
    assert {"term": {"status": "ACTIVE"}} in clauses
    assert {"range": {"effective_date": {"gte": "2022-01-01"}}} in clauses
