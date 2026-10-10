"""Related regulatory text for a rule, found by keyword search (informational only).

The JSON rule files carry no document citations. To support traceability
without inventing references, the rules service asks the search service for
paragraphs from the *same regulator* that match the rule's field names and
description. These are labelled "related text (keyword match)" in the UI and
API — they are search results, not an authoritative rule-to-clause mapping.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from iris_shared.config import get_settings

from ..engine import Rule

logger = logging.getLogger("rules.related")


def query_for(rule: Rule) -> str:
    words = []
    for f in rule.fields:
        if f == "Asset_Class":
            continue
        words.append(f.replace("_", " "))
    desc = re.sub(r"[^\w\s-]", " ", rule.description)
    return " ".join([*words, desc]).strip()


def related_clauses(rule: Rule, limit: int = 2) -> dict[str, Any]:
    payload = {
        "query": query_for(rule),
        "filters": {"regulators": [rule.regulator]},
        "scope": "latest",
        "match_mode": "any",
        "page": 1,
        "page_size": limit,
        "record_history": False,
    }
    try:
        with httpx.Client(base_url=get_settings().search_url, timeout=10) as client:
            r = client.post("/api/search", json=payload)
        if r.status_code != 200:
            return {"status": "unavailable", "detail": f"search returned {r.status_code}", "items": []}
        items = []
        for hit in r.json().get("results", []):
            c = hit["citation"]
            items.append(
                {
                    "paragraph_id": hit["paragraph_id"],
                    "heading": hit.get("heading"),
                    "document_name": c["document_name"],
                    "version": c["version"],
                    "location_label": c["location_label"],
                    "source_url": c["source_url"],
                    "viewer_url": c["viewer_url"],
                    "excerpt": "".join(s["text"] for s in hit.get("text_segments", []))[:400],
                }
            )
        return {
            "status": "ok",
            "method": "keyword search (BM25) on rule fields and description, same regulator; informational, not an authoritative citation",
            "query": payload["query"],
            "items": items,
        }
    except httpx.HTTPError as exc:
        logger.warning("related clause lookup failed: %s", exc)
        return {"status": "unavailable", "detail": type(exc).__name__, "items": []}
