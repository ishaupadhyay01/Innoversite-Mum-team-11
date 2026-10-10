"""Unit-tests the Elasticsearch backend against a fake client (real ES runs in the CI compose smoke test)."""

from app.backends.elastic import ElasticsearchBackend
from app.schemas import SearchFilters


class FakeES:
    def __init__(self) -> None:
        self.calls: dict = {}

    def search(self, **kw):  # type: ignore[no-untyped-def]
        self.calls["search"] = kw
        src = {"clause_id": "c1", "text": "LEI <b>required</b>"}
        return {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_source": src, "_score": 3.2, "highlight": {"text": ["<mark>LEI</mark> &lt;b&gt;"]}}],
            }
        }


def test_search_builds_filtered_query_with_escaped_highlights():
    backend = ElasticsearchBackend.__new__(ElasticsearchBackend)
    backend.es, backend.alias = FakeES(), "iris-clauses"
    result = backend.search("LEI", SearchFilters(regulator=["EMIR"], jurisdiction=["EU"]), offset=10, size=5)

    call = backend.es.calls["search"]
    assert call["from_"] == 10 and call["size"] == 5 and call["index"] == "iris-clauses"
    assert call["highlight"]["encoder"] == "html"
    filters = call["query"]["bool"]["filter"]
    assert {"terms": {"regulator_canonical": ["EMIR"]}} in filters
    assert {"term": {"status": "ACTIVE"}} in filters
    assert result.total == 1 and result.hits[0][2] == ["<mark>LEI</mark> &lt;b&gt;"]
