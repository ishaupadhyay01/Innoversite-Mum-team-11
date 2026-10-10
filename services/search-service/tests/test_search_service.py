"""SearchService behaviour against a fake Elasticsearch client (no cluster needed)."""

from __future__ import annotations

from typing import Any

from app.schemas import SearchRequest
from app.search.service import SearchService


def _hit(pid: str, version: str = "2", is_latest: bool = True, chash: str = "h1") -> dict[str, Any]:
    return {
        "_id": pid,
        "_score": 7.5,
        "_source": {
            "paragraph_id": pid,
            "document_id": "1",
            "document_version_id": version,
            "document_name": "MiFID_II_2023_v2.pdf",
            "document_title": "MiFID II 2023",
            "regulator": "MiFID II",
            "jurisdiction": "EU",
            "category": "Trade reporting",
            "version": "v2.0",
            "source_type": "pdf",
            "effective_date": "2023-07-01",
            "is_latest": is_latest,
            "ordinal": 3,
            "page_start": 1,
            "page_end": 1,
            "section_heading": "Paragraph 3. Counterparty LEI Requirement",
            "content": "The Counterparty_LEI must be a valid 20-character alphanumeric identifier.",
            "content_hash": chash,
        },
        "highlight": {"content.exact": ["The <mark>Counterparty</mark>_<mark>LEI</mark> must be valid."]},
    }


class FakeES:
    def __init__(self, first_total: int, relaxed_total: int = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self.first_total = first_total
        self.relaxed_total = relaxed_total

    def search(self, index: str, **body: Any) -> dict[str, Any]:
        self.calls.append(body)
        if body.get("size") == 0:  # duplicate-text aggregation
            return {
                "aggregations": {
                    "by_hash": {
                        "buckets": [
                            {
                                "key": "h1",
                                "refs": {
                                    "hits": {
                                        "hits": [
                                            {
                                                "_source": {
                                                    "paragraph_id": "v1-p0003",
                                                    "document_name": "MiFID_II_2023_v1.pdf",
                                                    "version": "v1.0",
                                                    "source_type": "pdf",
                                                    "page_start": 1,
                                                    "page_end": 1,
                                                }
                                            },
                                            {
                                                "_source": {
                                                    "paragraph_id": "v2-p0003",
                                                    "document_name": "MiFID_II_2023_v2.pdf",
                                                    "version": "v2.0",
                                                    "source_type": "pdf",
                                                    "page_start": 1,
                                                    "page_end": 1,
                                                }
                                            },
                                        ]
                                    }
                                },
                            }
                        ]
                    }
                }
            }
        first = len([c for c in self.calls if c.get("size") != 0]) == 1
        total = self.first_total if first else self.relaxed_total
        return {
            "took": 3,
            "hits": {"total": {"value": total}, "hits": [_hit("v2-p0003")] if total else []},
            "aggregations": {"scoped": {"doc_count": total, "regulator": {"buckets": [{"key": "MiFID II", "doc_count": total}]}}},
            "suggest": {"did_you_mean": [{"text": "counterpaty", "options": [{"text": "counterparty"}]}]},
        }


def test_search_returns_citations_highlights_and_identical_text() -> None:
    es = FakeES(first_total=1)
    res = SearchService(es, "alias", set()).search(SearchRequest(query="Counterparty LEI"))
    assert res.total == 1 and not res.relaxed
    hit = res.results[0]
    assert hit.citation.document_name == "MiFID_II_2023_v2.pdf"
    assert hit.citation.location_label == "Page 1"
    assert [s.text for s in hit.text_segments if s.highlight] == ["Counterparty", "LEI"]
    assert [d.document_name for d in hit.identical_text_in] == ["MiFID_II_2023_v1.pdf"]
    assert res.facets["regulator"][0].value == "MiFID II"
    assert res.did_you_mean is None  # only offered when nothing matched


def test_zero_strict_hits_retries_in_any_mode_and_says_so() -> None:
    es = FakeES(first_total=0, relaxed_total=1)
    res = SearchService(es, "alias", set()).search(SearchRequest(query="counterparty retention schedule"))
    assert res.relaxed is True and res.total == 1
    main_calls = [c for c in es.calls if c.get("size") != 0]
    assert len(main_calls) == 2
    assert "from_" in main_calls[0] and "from" not in main_calls[0]  # python-client parameter name
    relaxed_msm = main_calls[1]["query"]["bool"]["must"][0]["bool"]["should"][0]["multi_match"]["minimum_should_match"]
    assert relaxed_msm == "1"
    assert any("some of them" in n for n in res.notices)


def test_no_results_offers_spelling_suggestion_and_hints_without_inventing_results() -> None:
    es = FakeES(first_total=0, relaxed_total=0)
    req = SearchRequest(query="counterpaty lei", filters={"regulators": ["FCA"]})
    res = SearchService(es, "alias", set()).search(req)
    assert res.total == 0 and res.results == []
    assert res.did_you_mean == "counterparty"
    assert any("filters" in n for n in res.notices)
    assert any("All versions" in n for n in res.notices)
