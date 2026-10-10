"""Search execution: runs the BM25 query and shapes results with citations."""

from __future__ import annotations

import logging
import math
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..schemas import Citation, DuplicateRef, FacetBucket, SearchHit, SearchRequest, SearchResponse, Segment
from .highlight import best_highlight, plain_segments
from .query_builder import ParsedQuery, SearchFilters, build_search_body, build_suggest_body, parse_query

if TYPE_CHECKING:
    from elasticsearch import Elasticsearch

logger = logging.getLogger("search.service")


def load_noise_words(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}


def location_label(src: dict[str, Any]) -> str:
    st = src.get("source_type")
    if st == "pdf" and src.get("page_start"):
        ps, pe = src["page_start"], src.get("page_end")
        return f"Page {ps}" if not pe or pe == ps else f"Pages {ps}–{pe}"
    if st == "txt" and src.get("line_start"):
        ls, le = src["line_start"], src.get("line_end")
        return f"Lines {ls}–{le}" if le and le != ls else f"Line {ls}"
    if st == "html":
        return f"Section #{src['anchor']}" if src.get("anchor") else "HTML section (no page numbers)"
    return "Location not available"


def citation_for(src: dict[str, Any]) -> Citation:
    doc_id, ver_id = src["document_id"], src["document_version_id"]
    source_url = f"/api/documents/{doc_id}/source?version_id={ver_id}"
    if src.get("source_type") == "pdf" and src.get("page_start"):
        source_url += f"#page={src['page_start']}"
    elif src.get("source_type") == "html" and src.get("anchor"):
        source_url += f"#{src['anchor']}"
    return Citation(
        regulator=src.get("regulator", ""),
        document_name=src.get("document_name", ""),
        document_title=src.get("document_title"),
        version=src.get("version", ""),
        source_type=src.get("source_type", ""),
        page_start=src.get("page_start"),
        page_end=src.get("page_end"),
        line_start=src.get("line_start"),
        line_end=src.get("line_end"),
        section_heading=src.get("section_heading"),
        anchor=src.get("anchor"),
        location_label=location_label(src),
        source_url=source_url,
        viewer_url=f"/viewer/{ver_id}?paragraph={src['paragraph_id']}",
    )


class SearchService:
    def __init__(self, es: Elasticsearch, alias: str, noise_words: set[str]) -> None:
        self.es = es
        self.alias = alias
        self.noise_words = noise_words

    def _search(self, body: dict[str, Any]) -> dict[str, Any]:
        """Call ES search with request-body keys mapped to the Python client's parameter names."""
        params = dict(body)
        if "from" in params:
            params["from_"] = params.pop("from")
        if "_source" in params:
            params["source"] = params.pop("_source")
        return self.es.search(index=self.alias, **params)

    def _filters(self, req: SearchRequest) -> SearchFilters:
        f = req.filters
        return SearchFilters(
            regulators=f.regulators,
            jurisdictions=f.jurisdictions,
            categories=f.categories,
            source_types=list(f.source_types),
            versions=f.versions,
            document_ids=f.document_ids,
            effective_from=f.effective_from,
            effective_to=f.effective_to,
            uploaded_from=f.uploaded_from,
            uploaded_to=f.uploaded_to,
        )

    def search(self, req: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        parsed = parse_query(req.query, self.noise_words)
        filters = self._filters(req)
        body = build_search_body(
            parsed, filters, req.scope, req.version_id, req.sort, req.page, req.page_size, req.match_mode, with_suggest=True
        )
        res = self._search(body)
        relaxed = False
        total = res["hits"]["total"]["value"]
        notices: list[str] = []
        if total == 0 and parsed.terms and req.match_mode != "any" and len(parsed.terms) > 1:
            relaxed_body = build_search_body(
                parsed, filters, req.scope, req.version_id, req.sort, req.page, req.page_size, "any", with_suggest=False
            )
            relaxed_res = self._search(relaxed_body)
            if relaxed_res["hits"]["total"]["value"] > 0:
                relaxed = True
                suggest = res.get("suggest")
                res = relaxed_res
                if suggest:
                    res["suggest"] = suggest
                total = res["hits"]["total"]["value"]
                notices.append("No paragraph contains all of your terms; showing paragraphs that match some of them.")

        raw_hits = res["hits"]["hits"]
        hits = [self._hit(h) for h in raw_hits]
        self._attach_duplicates(hits, {h["_source"]["paragraph_id"]: h["_source"].get("content_hash") for h in raw_hits})
        facets = {
            name: [FacetBucket(value=str(b["key"]), count=b["doc_count"]) for b in agg["buckets"]]
            for name, agg in res.get("aggregations", {}).get("scoped", {}).items()
            if isinstance(agg, dict) and "buckets" in agg
        }
        did_you_mean = self._did_you_mean(parsed, res) if total == 0 else None
        if total == 0:
            if not filters.is_empty():
                notices.append("Try removing some filters — they may exclude matching paragraphs.")
            if req.scope == "latest":
                notices.append(
                    "Only the latest version of each document is searched; switch the scope to 'All versions' to include historical text."
                )
        if parsed.removed_noise:
            notices.append(f"Ignored common question words: {', '.join(parsed.removed_noise)}")
        took = (time.perf_counter() - started) * 1000
        return SearchResponse(
            query=req.query,
            interpreted={
                "terms": parsed.terms,
                "phrases": parsed.phrases,
                "excluded": parsed.excluded,
                "match_mode": "any" if relaxed else req.match_mode,
            },
            total=total,
            took_ms=round(took, 1),
            es_took_ms=res.get("took"),
            page=req.page,
            page_size=req.page_size,
            total_pages=max(1, math.ceil(total / req.page_size)) if total else 0,
            scope=req.scope,
            version_id=req.version_id,
            sort=req.sort,
            relaxed=relaxed,
            results=hits,
            facets=facets,
            did_you_mean=did_you_mean,
            notices=notices,
        )

    def _hit(self, h: dict[str, Any]) -> SearchHit:
        src = h["_source"]
        hl = h.get("highlight")
        heading = src.get("section_heading")
        content = src.get("content", "")
        eff = src.get("effective_date")
        return SearchHit(
            paragraph_id=src["paragraph_id"],
            score=h.get("_score"),
            document_id=src["document_id"],
            document_version_id=src["document_version_id"],
            regulator=src.get("regulator", ""),
            jurisdiction=src.get("jurisdiction"),
            category=src.get("category"),
            effective_date=date.fromisoformat(eff) if eff else None,
            is_latest=bool(src.get("is_latest")),
            heading=heading,
            heading_segments=[Segment(**s) for s in best_highlight(hl, ["section_heading.exact", "section_heading"], heading or "")]
            if heading
            else [],
            text_segments=[Segment(**s) for s in best_highlight(hl, ["content.exact", "content", "content.syn"], content)],
            citation=citation_for(src),
        )

    def _attach_duplicates(self, hits: list[SearchHit], hashes: dict[str, str | None]) -> None:
        """Flag identical paragraph text that also appears in other documents/versions."""
        hashes = {k: v for k, v in hashes.items() if v}
        if not hits or not hashes:
            return
        res = self.es.search(
            index=self.alias,
            size=0,
            query={"terms": {"content_hash": list(set(hashes.values()))}},
            aggs={
                "by_hash": {
                    "terms": {"field": "content_hash", "size": len(hashes) or 1, "min_doc_count": 2},
                    "aggs": {
                        "refs": {
                            "top_hits": {
                                "size": 6,
                                "_source": [
                                    "paragraph_id",
                                    "document_name",
                                    "version",
                                    "source_type",
                                    "page_start",
                                    "page_end",
                                    "line_start",
                                    "line_end",
                                    "anchor",
                                ],
                                "sort": [{"document_name.keyword": "asc"}, {"version": "asc"}],
                            }
                        }
                    },
                }
            },
        )
        by_hash: dict[str, list[dict[str, Any]]] = {
            b["key"]: [r["_source"] for r in b["refs"]["hits"]["hits"]] for b in res["aggregations"]["by_hash"]["buckets"]
        }
        for hit in hits:
            refs = by_hash.get(hashes.get(hit.paragraph_id, ""), [])
            hit.identical_text_in = [
                DuplicateRef(
                    paragraph_id=r["paragraph_id"],
                    document_name=r["document_name"],
                    version=r["version"],
                    location_label=location_label(r),
                )
                for r in refs
                if r["paragraph_id"] != hit.paragraph_id
            ]

    @staticmethod
    def _did_you_mean(parsed: ParsedQuery, res: dict[str, Any]) -> str | None:
        options = res.get("suggest", {}).get("did_you_mean", [])
        changed = False
        words = []
        for entry in options:
            if entry.get("options"):
                words.append(entry["options"][0]["text"])
                changed = True
            else:
                words.append(entry["text"])
        if not changed:
            return None
        suggestion = " ".join(words)
        return suggestion if suggestion.lower() != parsed.free_text.lower() else None

    def suggestions(self, prefix: str, size: int = 8) -> list[dict[str, str]]:
        res = self._search(build_suggest_body(prefix, size))
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for h in res["hits"]["hits"]:
            heading = (h["_source"].get("section_heading") or "").strip()
            key = heading.lower()
            if heading and key not in seen:
                seen.add(key)
                out.append({"text": heading, "type": "heading", "detail": h["_source"].get("document_name")})
            if len(out) >= size:
                break
        return out

    def facet_values(self) -> dict[str, Any]:
        res = self.es.search(
            index=self.alias,
            size=0,
            aggs={
                "regulator": {"terms": {"field": "regulator", "size": 50}},
                "jurisdiction": {"terms": {"field": "jurisdiction", "size": 50}},
                "category": {"terms": {"field": "category", "size": 50}},
                "source_type": {"terms": {"field": "source_type", "size": 10}},
                "version": {"terms": {"field": "version", "size": 50}},
                "documents": {
                    "terms": {"field": "document_version_id", "size": 500},
                    "aggs": {
                        "meta": {"top_hits": {"size": 1, "_source": ["document_name", "version", "regulator", "is_latest", "document_id"]}}
                    },
                },
                "effective_min": {"min": {"field": "effective_date"}},
                "effective_max": {"max": {"field": "effective_date"}},
            },
        )
        aggs = res["aggregations"]
        versions = []
        for b in aggs["documents"]["buckets"]:
            meta = b["meta"]["hits"]["hits"][0]["_source"]
            versions.append(
                {
                    "version_id": b["key"],
                    "document_id": meta["document_id"],
                    "label": f"{meta['document_name']} ({meta['version']})",
                    "regulator": meta["regulator"],
                    "is_latest": meta["is_latest"],
                    "paragraphs": b["doc_count"],
                }
            )
        versions.sort(key=lambda v: v["label"])
        return {
            name: [{"value": b["key"], "count": b["doc_count"]} for b in aggs[name]["buckets"]]
            for name in ("regulator", "jurisdiction", "category", "source_type", "version")
        } | {
            "document_versions": versions,
            "effective_date_range": {
                "min": aggs["effective_min"].get("value_as_string"),
                "max": aggs["effective_max"].get("value_as_string"),
            },
        }

    def get_paragraph(self, paragraph_id: str, context: int = 1) -> dict[str, Any] | None:
        res = self.es.search(index=self.alias, size=1, query={"term": {"paragraph_id": paragraph_id}})
        hits = res["hits"]["hits"]
        if not hits:
            return None
        src = hits[0]["_source"]
        neighbours = self.es.search(
            index=self.alias,
            size=2 * context + 1,
            query={
                "bool": {
                    "filter": [
                        {"term": {"document_version_id": src["document_version_id"]}},
                        {"range": {"ordinal": {"gte": src["ordinal"] - context, "lte": src["ordinal"] + context}}},
                    ]
                }
            },
            sort=[{"ordinal": "asc"}],
        )["hits"]["hits"]
        return {
            "paragraph": self._paragraph_dict(src),
            "context": [self._paragraph_dict(n["_source"]) for n in neighbours],
        }

    def version_paragraphs(self, version_id: str) -> list[dict[str, Any]]:
        res = self.es.search(index=self.alias, size=2000, query={"term": {"document_version_id": version_id}}, sort=[{"ordinal": "asc"}])
        return [self._paragraph_dict(h["_source"]) for h in res["hits"]["hits"]]

    @staticmethod
    def _paragraph_dict(src: dict[str, Any]) -> dict[str, Any]:
        return {
            "paragraph_id": src["paragraph_id"],
            "ordinal": src["ordinal"],
            "heading": src.get("section_heading"),
            "text": src.get("content", ""),
            "segments": list(plain_segments(src.get("content", ""))),
            "citation": citation_for(src).model_dump(),
            "is_latest": src.get("is_latest"),
        }
