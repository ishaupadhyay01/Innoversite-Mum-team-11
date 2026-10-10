"""Integration tests against a real Elasticsearch node.

Run when ES_TEST_URL is set (GitHub Actions starts an Elasticsearch service
container). Skipped otherwise.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from .conftest import CONFIG

ES_URL = os.environ.get("ES_TEST_URL")
pytestmark = pytest.mark.skipif(not ES_URL, reason="ES_TEST_URL not set (no Elasticsearch available)")

if ES_URL:
    from elasticsearch import Elasticsearch

    from app.indexing.indexer import Indexer
    from app.schemas import SearchRequest
    from app.search.service import SearchService, load_noise_words


PARAS = [
    # (version, ordinal, regulator, doc name, version label, heading, content, is_latest, page)
    (
        "2",
        2,
        "MiFID II",
        "MiFID_II_2023_v2.pdf",
        "v2.0",
        "Paragraph 2. Mandatory Trade Reporting Fields",
        "All investment firms shall report, for each trade, the following fields without omission: Trade_ID, Asset_Class, "
        "Execution_Timestamp, Counterparty_LEI, Price, Quantity, Currency.",
        True,
        1,
    ),
    (
        "2",
        3,
        "MiFID II",
        "MiFID_II_2023_v2.pdf",
        "v2.0",
        "Paragraph 3. Counterparty LEI Requirement",
        "The Counterparty_LEI must be a valid 20-character alphanumeric identifier issued by an accredited Local "
        "Operating Unit (LOU) in accordance with the Global Legal Entity Identifier System (GLEIF).",
        True,
        1,
    ),
    (
        "1",
        3,
        "MiFID II",
        "MiFID_II_2023_v1.pdf",
        "v1.0",
        "Paragraph 3. Counterparty LEI Requirement",
        "The Counterparty_LEI must be a valid 20-character alphanumeric identifier issued by an accredited Local "
        "Operating Unit (LOU) in accordance with the Global Legal Entity Identifier System (GLEIF).",
        False,
        1,
    ),
    (
        "6",
        4,
        "FCA",
        "FCA_Guidance_2023.html",
        "v1.1",
        "3. FX-Specific Relaxations",
        "For foreign-exchange (FX) trades, the FCA permits the omission of Counterparty_LEI and Underlying_ISIN when the "
        "transaction is executed on a recognised FX platform.",
        True,
        None,
    ),
    (
        "9",
        3,
        "SEC",
        "SEC_GUIDANCE_2023_v2.pdf",
        "v2.0",
        "Paragraph 3. Price Field Validation",
        "A negative price or a price exceeding the instrument's theoretical maximum will cause the trade report to be "
        "rejected with error code SEC-R01.",
        True,
        1,
    ),
]


def _doc(p: tuple[Any, ...]) -> dict[str, Any]:
    version, ordinal, regulator, name, label, heading, content, latest, page = p
    return {
        "paragraph_id": f"v{version}-p{ordinal:04d}",
        "document_id": {"1": "1", "2": "1"}.get(version, version),
        "document_version_id": version,
        "document_name": name,
        "document_title": name.rsplit(".", 1)[0].replace("_", " "),
        "regulator": regulator,
        "jurisdiction": "UK" if regulator == "FCA" else ("US" if regulator == "SEC" else "EU"),
        "category": "Trade reporting",
        "version": label,
        "source_type": name.rsplit(".", 1)[1],
        "effective_date": "2023-07-01",
        "uploaded_at": "2024-07-15T14:30:00+00:00",
        "is_latest": latest,
        "ordinal": ordinal,
        "page_start": page,
        "page_end": page,
        "line_start": None,
        "line_end": None,
        "anchor": "p3" if regulator == "FCA" else None,
        "section_heading": heading,
        "heading_suggest": heading,
        "content": content,
        "content_hash": str(hash(content)),
        "char_count": len(content),
        "indexed_at": "2024-07-15T14:30:00+00:00",
    }


@pytest.fixture(scope="module")
def service():  # type: ignore[no-untyped-def]
    es = Elasticsearch(ES_URL, request_timeout=30)
    alias = f"iris-test-{uuid.uuid4().hex[:8]}"
    indexer = Indexer(es, alias, CONFIG / "synonyms.txt")
    indexer.ensure_index()
    for version in {p[0] for p in PARAS}:
        docs = [_doc(p) for p in PARAS if p[0] == version]
        result = indexer.index_version(version, docs)
        assert result["errors"] == []
    yield SearchService(es, alias, load_noise_words(CONFIG / "query_noise_words.txt")), indexer
    es.indices.delete(index=indexer.concrete_name)
    es.close()


def test_keyword_search_ranks_lei_clause_first(service) -> None:  # type: ignore[no-untyped-def]
    svc, _ = service
    res = svc.search(SearchRequest(query="Counterparty LEI", record_history=False))
    assert res.total >= 2
    top = res.results[0]
    assert top.heading == "Paragraph 3. Counterparty LEI Requirement"
    assert top.citation.document_name == "MiFID_II_2023_v2.pdf"  # latest scope excludes v1
    assert top.citation.location_label == "Page 1"
    assert any(s.highlight for s in top.text_segments)


def test_exact_phrase_search(service) -> None:  # type: ignore[no-untyped-def]
    svc, _ = service
    res = svc.search(SearchRequest(query='"Mandatory Trade Reporting Fields"', record_history=False))
    assert res.total == 1
    assert res.results[0].heading.endswith("Mandatory Trade Reporting Fields")


def test_regulator_filter_and_all_versions_scope(service) -> None:  # type: ignore[no-untyped-def]
    svc, _ = service
    fca = svc.search(SearchRequest(query="Counterparty LEI", filters={"regulators": ["FCA"]}, record_history=False))
    assert {r.regulator for r in fca.results} == {"FCA"}
    assert fca.results[0].citation.page_start is None  # HTML: no page numbers
    all_versions = svc.search(SearchRequest(query='"Counterparty LEI Requirement"', scope="all", record_history=False))
    assert {r.citation.version for r in all_versions.results} == {"v1.0", "v2.0"}
    assert any(r.identical_text_in for r in all_versions.results)


def test_synonyms_expand_free_text_queries(service) -> None:  # type: ignore[no-untyped-def]
    svc, _ = service
    res = svc.search(SearchRequest(query="foreign exchange relaxations", record_history=False))
    assert res.results and res.results[0].regulator == "FCA"


def test_negative_price_and_no_result_handling(service) -> None:  # type: ignore[no-untyped-def]
    svc, _ = service
    res = svc.search(SearchRequest(query="negative price", record_history=False))
    assert res.results[0].citation.document_name == "SEC_GUIDANCE_2023_v2.pdf"
    none = svc.search(SearchRequest(query="zzqx unicorn", record_history=False))
    assert none.total == 0 and none.results == []


def test_suggestions_and_stats(service) -> None:  # type: ignore[no-untyped-def]
    svc, indexer = service
    suggestions = svc.suggestions("counterparty")
    assert any("Counterparty LEI Requirement" in s["text"] for s in suggestions)
    stats = indexer.stats()
    assert stats["paragraphs_total"] == len(PARAS)
    assert indexer.version_count("2") == 2
