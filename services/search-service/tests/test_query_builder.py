"""Elasticsearch query construction (pure, no cluster required)."""

from __future__ import annotations

from datetime import date

import pytest

from app.search.query_builder import (
    SearchFilters,
    build_filter_clauses,
    build_search_body,
    build_text_query,
    minimum_should_match,
    parse_query,
)

NOISE = {"give", "me", "the", "paragraph", "that", "defines", "under"}


def test_parse_query_separates_phrases_terms_and_exclusions() -> None:
    q = parse_query('Counterparty LEI "trade report" -retention', NOISE)
    assert q.terms == ["Counterparty", "LEI"]
    assert q.phrases == ["trade report"]
    assert q.excluded == ["retention"]


def test_noise_words_removed_from_natural_language_questions() -> None:
    q = parse_query("Give me the paragraph that defines the LEI requirement under MiFID II", NOISE)
    assert q.terms == ["LEI", "requirement", "MiFID", "II"]
    assert "paragraph" in [w.lower() for w in q.removed_noise]


def test_only_noise_words_keeps_original_words() -> None:
    q = parse_query("the paragraph", NOISE)
    assert q.terms == ["the", "paragraph"]


def test_keyword_query_is_bm25_cross_fields_with_heading_boost() -> None:
    query = build_text_query(parse_query("Counterparty LEI"), "smart")
    must = query["bool"]["must"][0]["bool"]["should"]
    mm = must[0]["multi_match"]
    assert mm["type"] == "cross_fields"
    assert "section_heading^3" in mm["fields"] and "content" in mm["fields"]
    assert mm["minimum_should_match"] == "3<75%"
    # exact-phrase proximity boost on unstemmed fields
    boosts = query["bool"]["should"]
    assert any(b.get("multi_match", {}).get("type") == "phrase" and "content.exact^2" in b["multi_match"]["fields"] for b in boosts)


def test_quoted_phrase_uses_exact_fields_without_synonyms() -> None:
    query = build_text_query(parse_query('"Counterparty LEI"'), "smart")
    phrase = query["bool"]["must"][0]["multi_match"]
    assert phrase["type"] == "phrase"
    assert phrase["fields"] == ["content.exact", "section_heading.exact^2"]
    assert all(".syn" not in f for f in phrase["fields"])


def test_exclusions_become_must_not() -> None:
    query = build_text_query(parse_query("reporting -swap"), "smart")
    assert query["bool"]["must_not"][0]["multi_match"]["query"] == "swap"


def test_match_modes() -> None:
    assert minimum_should_match("all") == "100%"
    assert minimum_should_match("any") == "1"
    with pytest.raises(ValueError):
        build_text_query(parse_query("x"), "fuzzy")


def test_filters_combine_and_scope_is_applied() -> None:
    f = SearchFilters(regulators=["MiFID II", "EMIR"], jurisdictions=["EU"], source_types=["pdf"], effective_from=date(2021, 1, 1))
    clauses = build_filter_clauses(f, "latest", None)
    assert {"terms": {"regulator": ["MiFID II", "EMIR"]}} in clauses
    assert {"terms": {"jurisdiction": ["EU"]}} in clauses
    assert {"range": {"effective_date": {"gte": "2021-01-01"}}} in clauses
    assert {"term": {"is_latest": True}} in clauses
    assert {"term": {"document_version_id": "7"}} in build_filter_clauses(SearchFilters(), "version", "7")
    assert build_filter_clauses(SearchFilters(), "all", None) == []
    with pytest.raises(ValueError):
        build_filter_clauses(SearchFilters(), "version", None)


def test_search_body_pagination_sorting_highlight_and_facets() -> None:
    body = build_search_body(parse_query("LEI"), SearchFilters(regulators=["FCA"]), "all", None, "newest", page=3, page_size=10)
    assert body["from"] == 20 and body["size"] == 10
    assert body["sort"][0] == {"uploaded_at": "desc"}
    assert body["post_filter"]["bool"]["filter"] == [{"terms": {"regulator": ["FCA"]}}]
    assert body["highlight"]["encoder"] == "html"
    assert "regulator" in body["aggs"]["scoped"]["aggs"]
    assert body["track_total_hits"] is True


def test_empty_query_browses_by_document_name() -> None:
    body = build_search_body(parse_query(""), SearchFilters(regulators=["SEC"]), "latest")
    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert body["sort"][0] == {"document_name.keyword": "asc"}


@pytest.mark.parametrize(("page", "size"), [(0, 10), (1, 0), (1, 51), (1001, 10)])
def test_invalid_paging_rejected(page: int, size: int) -> None:
    with pytest.raises(ValueError):
        build_search_body(parse_query("x"), SearchFilters(), page=page, page_size=size)
