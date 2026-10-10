from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch, helpers

from app.backends.base import ClauseDocument, SearchResult
from app.backends.filters import es_filter_clauses
from app.schemas import SearchFilters

log = logging.getLogger(__name__)
MAPPING = json.loads((Path(__file__).parent / "es_mapping.json").read_text())
FACET_FIELDS = ("regulator", "jurisdiction", "category", "status")


class ElasticsearchBackend:
    """Index = '<alias>-v1' behind an alias, so the mapping can evolve with zero-downtime reindexing."""

    def __init__(self, url: str, alias: str) -> None:
        self.es = Elasticsearch(url, request_timeout=10, retry_on_timeout=True, max_retries=3)
        self.alias = alias
        self.index_name = f"{alias}-v1"

    def ping(self) -> bool:
        return bool(self.es.ping())

    def ensure_index(self) -> None:
        if self.es.indices.exists_alias(name=self.alias):
            return
        if not self.es.indices.exists(index=self.index_name):
            self.es.indices.create(index=self.index_name, settings=MAPPING["settings"], mappings=MAPPING["mappings"])
        self.es.indices.put_alias(index=self.index_name, name=self.alias)
        log.info("es_index_created", extra={"index": self.index_name, "alias": self.alias})

    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None:
        self.ensure_index()
        # Idempotent: remove clauses of this version that no longer exist, then upsert by clause_id.
        self.es.delete_by_query(
            index=self.alias, query={"term": {"version_id": version_id}}, refresh=True, conflicts="proceed"
        )
        actions = ({"_index": self.alias, "_id": d.clause_id, "_source": d.to_source()} for d in docs)
        helpers.bulk(self.es, actions, refresh="wait_for")

    def set_document_status(self, document_id: str, active_version_id: str | None) -> None:
        script = {
            "source": "ctx._source.status = (params.active != null && ctx._source.version_id == params.active) "
            "? 'ACTIVE' : 'INACTIVE'",
            "params": {"active": active_version_id},
        }
        self.es.update_by_query(
            index=self.alias,
            query={"term": {"document_id": document_id}},
            script=script,
            refresh=True,
            conflicts="proceed",
        )

    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult:
        body_query: dict[str, Any] = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": ["text", "clause_title^2", "document_title", "clause_ref.text^3"],
                            "type": "best_fields",
                            "operator": "or",
                            "minimum_should_match": "30%",
                        }
                    }
                ],
                "should": [{"match_phrase": {"text": {"query": q, "slop": 3, "boost": 2}}}],
                "filter": es_filter_clauses(filters),
            }
        }
        resp = self.es.search(
            index=self.alias,
            query=body_query,
            from_=offset,
            size=size,
            track_total_hits=True,
            highlight={
                "fields": {"text": {"fragment_size": 220, "number_of_fragments": 2}},
                "encoder": "html",  # escape source text; only our <mark> tags are HTML
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
        )
        hits = [
            (h["_source"], float(h["_score"] or 0), h.get("highlight", {}).get("text", []))
            for h in resp["hits"]["hits"]
        ]
        return SearchResult(total=resp["hits"]["total"]["value"], hits=hits)

    def facets(self) -> dict[str, list[tuple[str, int]]]:
        self.ensure_index()
        resp = self.es.search(
            index=self.alias, size=0, aggs={f: {"terms": {"field": f, "size": 100}} for f in FACET_FIELDS}
        )
        return {f: [(b["key"], b["doc_count"]) for b in resp["aggregations"][f]["buckets"]] for f in FACET_FIELDS}
