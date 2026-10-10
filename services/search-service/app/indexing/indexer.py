"""Index lifecycle and bulk indexing against Elasticsearch."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import BulkIndexError, bulk

from .mapping import INDEX_VERSION, index_body, load_synonyms

logger = logging.getLogger("search.indexer")


class Indexer:
    def __init__(self, es: Elasticsearch, alias: str, synonyms_path: Any = None) -> None:
        self.es = es
        self.alias = alias
        self.synonyms_path = synonyms_path

    @property
    def concrete_name(self) -> str:
        return f"{self.alias}-v{INDEX_VERSION}"

    def ensure_index(self) -> bool:
        """Create the versioned index and alias if missing. Returns True when created."""
        if self.es.indices.exists_alias(name=self.alias):
            return False
        if not self.es.indices.exists(index=self.concrete_name):
            body = index_body(load_synonyms(self.synonyms_path))
            self.es.indices.create(index=self.concrete_name, settings=body["settings"], mappings=body["mappings"])
            logger.info("created index %s", self.concrete_name)
        self.es.indices.put_alias(index=self.concrete_name, name=self.alias)
        return True

    def reset(self) -> None:
        """Drop and recreate the index (used when PostgreSQL is empty, or after synonym changes)."""
        with contextlib.suppress(NotFoundError):
            self.es.indices.delete(index=self.concrete_name)
        self.ensure_index()

    def index_version(self, version_id: str, paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace all paragraphs of one version (idempotent: stable _id = paragraph_id)."""
        self.ensure_index()
        self.es.delete_by_query(
            index=self.alias,
            query={"term": {"document_version_id": version_id}},
            refresh=True,
            conflicts="proceed",
        )
        actions = ({"_op_type": "index", "_index": self.alias, "_id": p["paragraph_id"], "_source": p} for p in paragraphs)
        errors: list[str] = []
        try:
            ok, _ = bulk(self.es, actions, refresh="wait_for", raise_on_error=True, chunk_size=500)
        except BulkIndexError as exc:
            ok = len(paragraphs) - len(exc.errors)
            errors = [str(e)[:300] for e in exc.errors[:20]]
        return {"indexed": ok, "errors": errors}

    def set_latest(self, document_id: str, version_id: str) -> dict[str, int]:
        script = {
            "lang": "painless",
            "source": "ctx._source.is_latest = ctx._source.document_version_id == params.v",
            "params": {"v": version_id},
        }
        res = self.es.update_by_query(
            index=self.alias,
            query={"term": {"document_id": document_id}},
            script=script,
            refresh=True,
            conflicts="proceed",
        )
        return {"updated": int(res.get("updated", 0))}

    def version_count(self, version_id: str) -> int:
        return int(self.es.count(index=self.alias, query={"term": {"document_version_id": version_id}})["count"])

    def delete_version(self, version_id: str) -> int:
        res = self.es.delete_by_query(
            index=self.alias, query={"term": {"document_version_id": version_id}}, refresh=True, conflicts="proceed"
        )
        return int(res.get("deleted", 0))

    def reconcile(self, valid_version_ids: list[str]) -> int:
        res = self.es.delete_by_query(
            index=self.alias,
            query={"bool": {"must_not": [{"terms": {"document_version_id": valid_version_ids}}]}},
            refresh=True,
            conflicts="proceed",
        )
        return int(res.get("deleted", 0))

    def stats(self) -> dict[str, Any]:
        total = int(self.es.count(index=self.alias)["count"])
        latest = int(self.es.count(index=self.alias, query={"term": {"is_latest": True}})["count"])
        aggs = self.es.search(
            index=self.alias,
            size=0,
            aggs={
                "regulator": {"terms": {"field": "regulator", "size": 50}},
                "versions": {"cardinality": {"field": "document_version_id"}},
                "documents": {"cardinality": {"field": "document_id"}},
            },
        )["aggregations"]
        return {
            "paragraphs_total": total,
            "paragraphs_latest": latest,
            "versions_indexed": int(aggs["versions"]["value"]),
            "documents_indexed": int(aggs["documents"]["value"]),
            "paragraphs_by_regulator": [{"regulator": b["key"], "paragraphs": b["doc_count"]} for b in aggs["regulator"]["buckets"]],
            "index": self.concrete_name,
        }
