"""Pure routing rules for the gateway (unit-tested without FastAPI)."""

from __future__ import annotations

ROUTES: list[tuple[str, str]] = [
    ("/api/documents", "ingestion"),
    ("/api/alerts", "ingestion"),
    ("/api/imports", "ingestion"),
    ("/api/audit", "ingestion"),
    ("/api/search", "search"),
    ("/api/rules", "rules"),
    ("/api/impact-matrix", "rules"),
    ("/api/gap-analysis", "rules"),
    ("/api/checklist", "rules"),
    ("/api/trades", "rules"),
]

# Mutating endpoints that require the optional API_TOKEN (read-only computations stay open).
PROTECTED: list[tuple[str, str]] = [
    ("POST", "/api/documents/upload"),
    ("POST", "/api/imports/run"),
    ("POST", "/api/rules/reload"),
    ("POST", "/api/impact-matrix"),
    ("PATCH", "/api/alerts/"),
    ("POST", "/api/alerts/read-all"),
]

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


def service_for(path: str) -> str | None:
    """Return the owning service for a public /api path, or None.

    /internal/* paths are never routed, so service-to-service endpoints are not reachable through the gateway.
    """
    if not path.startswith("/api/"):
        return None
    for prefix, service in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            return service
    return None


def requires_token(method: str, path: str) -> bool:
    method = method.upper()
    return any(method == m and (path == p or (p.endswith("/") and path.startswith(p))) for m, p in PROTECTED)
