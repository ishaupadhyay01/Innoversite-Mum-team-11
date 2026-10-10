"""Construction of Elasticsearch BM25 queries (pure functions, unit-tested).

Query anatomy for ``Counterparty LEI "trade report" -retention``::

    bool
      must:
        - bool.should (min 1):                         # recall
            * multi_match cross_fields, term-centric over
              content, section_heading^3, document_title^1.5, regulator.text^2
              with minimum_should_match ("smart": all terms up to 3, then 75%)
            * match content.syn (synonym-expanded, operator AND)
        - multi_match phrase on content.exact / section_heading.exact^2   # each "quoted phrase"
      must_not:
        - multi_match on excluded -terms
      should:                                           # ranking boosts
        - multi_match phrase of all free terms (slop 0) on content.exact^2, section_heading.exact^4
        - multi_match phrase (slop 3) on content.exact
      filter: (applied as post_filter so facet counts stay informative)
        - terms regulator / jurisdiction / category / source_type / version
        - range effective_date / uploaded_at
        - scope: is_latest=true | document_version_id=<id> | (all)

Quoted phrases search unstemmed fields without synonyms, so an exact phrase
keeps its literal meaning. When the strict query finds nothing, the service
retries once in ``any`` mode and marks the response ``relaxed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

PHRASE_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
TOKEN_RE = re.compile(r"-?[\w][\w.\-/]*", re.UNICODE)

MAIN_FIELDS = ["content", "section_heading^3", "document_title^1.5", "regulator.text^2"]
PHRASE_FIELDS = ["content.exact", "section_heading.exact^2"]
SORTS = {
    "relevance": [{"_score": "desc"}, {"effective_date": {"order": "desc", "missing": "_last"}}, {"ordinal": "asc"}],
    "newest": [{"uploaded_at": "desc"}, {"_score": "desc"}, {"ordinal": "asc"}],
    "effective_date": [{"effective_date": {"order": "desc", "missing": "_last"}}, {"_score": "desc"}, {"ordinal": "asc"}],
    "document_name": [{"document_name.keyword": "asc"}, {"version": "asc"}, {"ordinal": "asc"}],
}
MATCH_MODES = {"smart", "all", "any"}


@dataclass
class ParsedQuery:
    raw: str
    phrases: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    removed_noise: list[str] = field(default_factory=list)

    @property
    def free_text(self) -> str:
        return " ".join(self.terms)

    @property
    def is_empty(self) -> bool:
        return not (self.phrases or self.terms)


def parse_query(raw: str, noise_words: set[str] | None = None) -> ParsedQuery:
    noise_words = noise_words or set()
    text = (raw or "").strip()
    phrases = [a or b for a, b in PHRASE_RE.findall(text)]
    remainder = PHRASE_RE.sub(" ", text)
    terms: list[str] = []
    excluded: list[str] = []
    removed: list[str] = []
    for token in TOKEN_RE.findall(remainder):
        if token.startswith("-") and len(token) > 1:
            excluded.append(token[1:])
            continue
        token = token.strip(".-/")
        if not token:
            continue
        if token.lower() in noise_words:
            removed.append(token)
            continue
        terms.append(token)
    # If every word was a noise word, keep the original words rather than searching for nothing.
    if not terms and not phrases and removed:
        terms, removed = removed, []
    return ParsedQuery(raw=text, phrases=[p.strip() for p in phrases if p.strip()], terms=terms, excluded=excluded, removed_noise=removed)


def minimum_should_match(mode: str) -> str:
    if mode == "all":
        return "100%"
    if mode == "any":
        return "1"
    return "3<75%"  # smart: up to 3 terms all required; more terms -> 75%


@dataclass
class SearchFilters:
    regulators: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    effective_from: date | None = None
    effective_to: date | None = None
    uploaded_from: date | None = None
    uploaded_to: date | None = None

    def is_empty(self) -> bool:
        return not any(
            [
                self.regulators,
                self.jurisdictions,
                self.categories,
                self.source_types,
                self.versions,
                self.document_ids,
                self.effective_from,
                self.effective_to,
                self.uploaded_from,
                self.uploaded_to,
            ]
        )


def build_filter_clauses(filters: SearchFilters, scope: str, version_id: str | None) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for fld, values in (
        ("regulator", filters.regulators),
        ("jurisdiction", filters.jurisdictions),
        ("category", filters.categories),
        ("source_type", filters.source_types),
        ("version", filters.versions),
        ("document_id", filters.document_ids),
    ):
        if values:
            clauses.append({"terms": {fld: list(values)}})
    if filters.effective_from or filters.effective_to:
        rng: dict[str, str] = {}
        if filters.effective_from:
            rng["gte"] = filters.effective_from.isoformat()
        if filters.effective_to:
            rng["lte"] = filters.effective_to.isoformat()
        clauses.append({"range": {"effective_date": rng}})
    if filters.uploaded_from or filters.uploaded_to:
        rng = {}
        if filters.uploaded_from:
            rng["gte"] = filters.uploaded_from.isoformat()
        if filters.uploaded_to:
            rng["lte"] = filters.uploaded_to.isoformat() + "T23:59:59Z"
        clauses.append({"range": {"uploaded_at": rng}})
    if scope == "latest":
        clauses.append({"term": {"is_latest": True}})
    elif scope == "version":
        if not version_id:
            raise ValueError("scope 'version' requires version_id")
        clauses.append({"term": {"document_version_id": str(version_id)}})
    elif scope != "all":
        raise ValueError(f"unknown scope {scope!r}")
    return clauses


def build_text_query(parsed: ParsedQuery, mode: str = "smart") -> dict[str, Any]:
    if mode not in MATCH_MODES:
        raise ValueError(f"unknown match mode {mode!r}")
    if parsed.is_empty:
        query: dict[str, Any] = {"bool": {"must": [{"match_all": {}}]}}
    else:
        must: list[dict[str, Any]] = []
        should: list[dict[str, Any]] = []
        if parsed.terms:
            text = parsed.free_text
            must.append(
                {
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": text,
                                    "type": "cross_fields",
                                    "fields": MAIN_FIELDS,
                                    "operator": "or",
                                    "minimum_should_match": minimum_should_match(mode),
                                }
                            },
                            {
                                "match": {
                                    "content.syn": {
                                        "query": text,
                                        "operator": "or" if mode == "any" else "and",
                                        "boost": 0.8,
                                    }
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
            should.append(
                {
                    "multi_match": {
                        "query": text,
                        "type": "phrase",
                        "fields": ["content.exact^2", "section_heading.exact^4"],
                        "slop": 0,
                        "boost": 2,
                    }
                }
            )
            should.append({"multi_match": {"query": text, "type": "phrase", "fields": ["content.exact"], "slop": 3}})
            should.append({"match": {"section_heading.syn": {"query": text, "boost": 1.5}}})
        for phrase in parsed.phrases:
            must.append({"multi_match": {"query": phrase, "type": "phrase", "fields": PHRASE_FIELDS}})
        query = {"bool": {"must": must, "should": should}}
    if parsed.excluded:
        query["bool"]["must_not"] = [
            {"multi_match": {"query": " ".join(parsed.excluded), "fields": ["content.exact", "section_heading.exact"]}}
        ]
    return query


HIGHLIGHT = {
    "type": "unified",
    "encoder": "html",
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "number_of_fragments": 0,
    "require_field_match": False,
    "fields": {
        "content": {},
        "content.exact": {},
        "content.syn": {},
        "section_heading": {},
        "section_heading.exact": {},
    },
}

FACETS = {
    "regulator": {"terms": {"field": "regulator", "size": 50}},
    "jurisdiction": {"terms": {"field": "jurisdiction", "size": 50}},
    "category": {"terms": {"field": "category", "size": 50}},
    "source_type": {"terms": {"field": "source_type", "size": 10}},
    "version": {"terms": {"field": "version", "size": 50}},
    "document": {"terms": {"field": "document_name.keyword", "size": 100}},
}


def build_search_body(
    parsed: ParsedQuery,
    filters: SearchFilters,
    scope: str = "latest",
    version_id: str | None = None,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = 10,
    mode: str = "smart",
    with_suggest: bool = False,
) -> dict[str, Any]:
    if sort not in SORTS:
        raise ValueError(f"unknown sort {sort!r}")
    if page < 1 or not 1 <= page_size <= 50:
        raise ValueError("page must be >= 1 and page_size between 1 and 50")
    offset = (page - 1) * page_size
    if offset + page_size > 10000:
        raise ValueError("cannot page beyond 10,000 results; refine the query")
    filter_clauses = build_filter_clauses(filters, scope, version_id)
    body: dict[str, Any] = {
        "query": build_text_query(parsed, mode),
        "post_filter": {"bool": {"filter": filter_clauses}},
        "sort": SORTS[sort] if not (sort == "relevance" and parsed.is_empty) else SORTS["document_name"],
        "from": offset,
        "size": page_size,
        "track_total_hits": True,
        "highlight": HIGHLIGHT,
        "aggs": {
            # facets are computed on the text query within the version scope, ignoring other filters
            "scoped": {
                "filter": {"bool": {"filter": [c for c in filter_clauses if _is_scope_clause(c)]}},
                "aggs": FACETS,
            }
        },
    }
    if with_suggest and parsed.free_text:
        body["suggest"] = {
            "did_you_mean": {
                "text": parsed.free_text,
                "term": {"field": "content.exact", "suggest_mode": "popular", "min_word_length": 3},
            }
        }
    return body


def _is_scope_clause(clause: dict[str, Any]) -> bool:
    term = clause.get("term") or {}
    return "is_latest" in term or "document_version_id" in term


def build_suggest_body(prefix: str, size: int = 8) -> dict[str, Any]:
    return {
        "size": size * 3,
        "_source": ["section_heading", "document_name", "regulator"],
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": prefix,
                            "type": "bool_prefix",
                            "fields": [
                                "heading_suggest",
                                "heading_suggest._2gram",
                                "heading_suggest._3gram",
                            ],
                        }
                    }
                ],
                "filter": [{"term": {"is_latest": True}}],
            }
        },
    }
