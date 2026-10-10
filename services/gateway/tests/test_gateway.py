"""Gateway routing and OpenAPI merge (pure)."""

from __future__ import annotations

from app.openapi_merge import merge_specs
from app.routing import requires_token, service_for


def test_routes_map_to_owning_service() -> None:
    assert service_for("/api/documents/upload") == "ingestion"
    assert service_for("/api/alerts/3/read") == "ingestion"
    assert service_for("/api/search") == "search"
    assert service_for("/api/search/suggestions") == "search"
    assert service_for("/api/impact-matrix/abc/export") == "rules"
    assert service_for("/api/checklist") == "rules"
    assert service_for("/api/searchx") is None
    assert service_for("/internal/index") is None  # internal APIs are never exposed


def test_token_protects_only_mutating_operations() -> None:
    assert requires_token("POST", "/api/documents/upload")
    assert requires_token("patch", "/api/alerts/12/read")
    assert requires_token("POST", "/api/impact-matrix")
    assert not requires_token("POST", "/api/search")
    assert not requires_token("GET", "/api/documents")
    assert not requires_token("GET", "/api/impact-matrix/x")


def test_merge_keeps_public_paths_and_resolves_schema_conflicts() -> None:
    base = {
        "openapi": "3.1.0",
        "info": {"title": "g", "version": "1", "description": ""},
        "paths": {"/api/health": {"get": {"tags": ["System"]}}},
        "components": {"schemas": {}},
    }
    a = {
        "paths": {
            "/api/search": {"post": {"tags": ["Search"], "responses": {"200": {"$ref": "#/components/schemas/Out"}}}},
            "/internal/index": {"post": {}},
        },
        "components": {"schemas": {"Out": {"type": "object", "title": "A"}}},
    }
    b = {
        "paths": {"/api/rules": {"get": {"tags": ["Rules"], "responses": {"200": {"$ref": "#/components/schemas/Out"}}}}},
        "components": {"schemas": {"Out": {"type": "object", "title": "B"}}},
    }
    merged = merge_specs(base, {"search": a, "rules": b})
    assert "/internal/index" not in merged["paths"]
    assert set(merged["paths"]) == {"/api/health", "/api/search", "/api/rules"}
    assert merged["paths"]["/api/rules"]["get"]["responses"]["200"]["$ref"] == "#/components/schemas/RulesOut"
    assert merged["components"]["schemas"]["Out"]["title"] == "A"
    assert merged["paths"]["/api/search"]["post"]["x-service"] == "search"
