"""Dependency-free backend for tests and for frontend devs who don't want to run Elasticsearch."""

from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

from app.backends.base import ClauseDocument, SearchResult
from app.backends.filters import matches
from app.schemas import SearchFilters
from iris_common.text import tokens

FACET_FIELDS = ("regulator", "jurisdiction", "category", "status")


class InMemoryBackend:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def ping(self) -> bool:
        return True

    def ensure_index(self) -> None:
        return None

    def index_clauses(self, version_id: str, docs: list[ClauseDocument]) -> None:
        self.docs = {k: v for k, v in self.docs.items() if v["version_id"] != version_id}
        for d in docs:
            self.docs[d.clause_id] = d.to_source()

    def set_document_status(self, document_id: str, active_version_id: str | None) -> None:
        for d in self.docs.values():
            if d["document_id"] == document_id:
                d["status"] = "ACTIVE" if d["version_id"] == active_version_id else "INACTIVE"

    def search(self, q: str, filters: SearchFilters, offset: int, size: int) -> SearchResult:
        q_tokens = set(tokens(q))
        scored = []
        for d in self.docs.values():
            if not matches(d, filters):
                continue
            body = Counter(tokens(f"{d['clause_title'] or ''} {d['text']}"))
            score = sum(body[t] for t in q_tokens) + 2 * sum(t in tokens(d["clause_title"] or "") for t in q_tokens)
            if score:
                scored.append((d, float(score), [self._highlight(d["text"], q_tokens)]))
        scored.sort(key=lambda x: x[1], reverse=True)
        return SearchResult(total=len(scored), hits=scored[offset : offset + size])

    @staticmethod
    def _highlight(text: str, q_tokens: set[str]) -> str:
        escaped = html.escape(text[:400])
        for t in sorted(q_tokens, key=len, reverse=True):
            escaped = re.sub(
                rf"(?<![A-Za-z0-9])({re.escape(t)})(?![A-Za-z0-9])", r"<mark>\1</mark>", escaped, flags=re.IGNORECASE
            )
        return escaped

    def facets(self) -> dict[str, list[tuple[str, int]]]:
        return {f: Counter(d[f] for d in self.docs.values() if d.get(f)).most_common() for f in FACET_FIELDS}
