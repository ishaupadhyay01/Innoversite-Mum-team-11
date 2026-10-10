"""HTTP client for the search service's internal indexing API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from iris_shared.config import get_settings
from iris_shared.web import internal_headers

logger = logging.getLogger("ingestion.search_client")


class SearchServiceError(RuntimeError):
    pass


def _client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(base_url=get_settings().search_url, headers=internal_headers(), timeout=timeout)


def _check(response: httpx.Response, action: str) -> dict[str, Any]:
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message")
        except ValueError:
            detail = response.text[:200]
        raise SearchServiceError(f"search service {action} failed ({response.status_code}): {detail}")
    return response.json()


def is_ready() -> bool:
    try:
        with _client(timeout=5) as client:
            r = client.get("/health")
            return r.status_code == 200 and r.json().get("checks", {}).get("elasticsearch", {}).get("ok") is True
    except httpx.HTTPError:
        return False


def index_version(version_meta: dict[str, Any], paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        with _client() as client:
            r = client.post("/internal/index", json={"version": version_meta, "paragraphs": paragraphs})
    except httpx.HTTPError as exc:
        raise SearchServiceError(f"search service unreachable: {exc}") from exc
    return _check(r, "indexing")


def set_latest(document_id: int, version_id: int) -> dict[str, Any]:
    try:
        with _client() as client:
            r = client.post("/internal/latest", json={"document_id": str(document_id), "version_id": str(version_id)})
    except httpx.HTTPError as exc:
        raise SearchServiceError(f"search service unreachable: {exc}") from exc
    return _check(r, "latest-version update")


def version_paragraph_count(version_id: int) -> int | None:
    try:
        with _client(timeout=10) as client:
            r = client.get(f"/internal/versions/{version_id}/count")
        return int(_check(r, "count")["count"])
    except (httpx.HTTPError, SearchServiceError, KeyError, ValueError):
        return None


def reset_index() -> None:
    with _client() as client:
        _check(client.post("/internal/reset"), "index reset")


def reconcile(valid_version_ids: list[int]) -> dict[str, Any]:
    """Remove indexed paragraphs whose version no longer exists in PostgreSQL."""
    with _client() as client:
        return _check(
            client.post("/internal/reconcile", json={"valid_version_ids": [str(v) for v in valid_version_ids]}),
            "reconcile",
        )
