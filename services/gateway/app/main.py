"""API gateway: one frontend-facing /api, aggregated dashboard and system status, merged OpenAPI."""

from __future__ import annotations

import asyncio
import hmac
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from iris_shared.config import get_settings
from iris_shared.logs import configure_logging
from iris_shared.web import error_body, install_error_handlers, internal_headers

from .openapi_merge import merge_specs
from .routing import HOP_BY_HOP, requires_token, service_for

STATIC_DIR = Path(__file__).parent / "static"
SERVICE_URLS: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("gateway", settings.log_level)
    SERVICE_URLS.update({"ingestion": settings.ingestion_url, "search": settings.search_url, "rules": settings.rules_url})
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))
    app.state.openapi_cache = (0.0, None)
    yield
    await app.state.client.aclose()


app = FastAPI(
    title="Reg IRIS API",
    version="1.0.0",
    description=(
        "Unified API for **Reg IRIS — Intelligent Regulatory Repository & Impact Scanner**.\n\n"
        "* Keyword search is Elasticsearch BM25 (no vector search, no LLM).\n"
        "* Every search hit carries a citation (file, version, page / section).\n"
        "* Rules are evaluated from JSON by a generic interpreter.\n\n"
        "Requests are routed to the ingestion, search and rules services; `x-service` on each operation names the owner."
    ),
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID", "X-Response-Time-Ms"],
)
if (STATIC_DIR / "swagger").exists():
    app.mount("/api/docs-static", StaticFiles(directory=STATIC_DIR / "swagger"), name="swagger-static")


# ----------------------------------------------------------------------------- docs


@app.get("/api/openapi.json", include_in_schema=False)
async def openapi_json(request: Request) -> JSONResponse:
    cached_at, cached = request.app.state.openapi_cache
    if cached is not None and time.monotonic() - cached_at < 30:
        return JSONResponse(cached)
    client: httpx.AsyncClient = request.app.state.client
    specs: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name, url in SERVICE_URLS.items():
        try:
            r = await client.get(f"{url}/openapi.json", timeout=5)
            r.raise_for_status()
            specs[name] = r.json()
        except (httpx.HTTPError, ValueError):
            missing.append(name)
    base = app.openapi()
    merged = merge_specs(base, specs)
    merged["servers"] = [{"url": "/"}]
    if missing:
        merged["info"]["description"] += f"\n\n> ⚠️ Not included (service unavailable): {', '.join(missing)}"
    else:
        request.app.state.openapi_cache = (time.monotonic(), merged)
    return JSONResponse(merged)


@app.get("/api/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    if (STATIC_DIR / "swagger").exists():
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title="Reg IRIS API — Swagger UI",
            swagger_js_url="/api/docs-static/swagger-ui-bundle.js",
            swagger_css_url="/api/docs-static/swagger-ui.css",
            swagger_favicon_url="/api/docs-static/favicon-32x32.png",
        )
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="Reg IRIS API — Swagger UI")


# ----------------------------------------------------------------------------- aggregation


async def _get(client: httpx.AsyncClient, service: str, path: str, internal: bool = False) -> tuple[str, Any, str | None, float]:
    started = time.perf_counter()
    try:
        r = await client.get(f"{SERVICE_URLS[service]}{path}", headers=internal_headers() if internal else None, timeout=10)
        ms = (time.perf_counter() - started) * 1000
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text[:200])
            except ValueError:
                msg = r.text[:200]
            return path, None, f"{service} {path}: HTTP {r.status_code} — {msg}", ms
        return path, r.json(), None, ms
    except httpx.HTTPError as exc:
        return path, None, f"{service} {path}: {type(exc).__name__}", (time.perf_counter() - started) * 1000


@app.get("/api/health", tags=["System"], summary="Gateway liveness")
async def gateway_health() -> dict[str, str]:
    return {"service": "gateway", "status": "ok"}


@app.get("/api/dashboard/stats", tags=["Dashboard"], summary="Executive dashboard statistics (aggregated from all services)")
async def dashboard_stats(request: Request) -> dict[str, Any]:
    client: httpx.AsyncClient = request.app.state.client
    calls = await asyncio.gather(
        _get(client, "ingestion", "/api/documents/stats"),
        _get(client, "ingestion", "/api/alerts?page_size=6"),
        _get(client, "ingestion", "/api/audit?limit=12"),
        _get(client, "search", "/internal/stats", internal=True),
        _get(client, "search", "/api/search/analytics?days=14"),
        _get(client, "rules", "/api/impact-matrix/latest"),
        _get(client, "rules", "/api/rules"),
    )
    data = {path: payload for path, payload, _, _ in calls}
    errors = [err for _, _, err, _ in calls if err]
    rules = data.get("/api/rules") or {}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "documents": data.get("/api/documents/stats"),
        "index": data.get("/internal/stats"),
        "search": data.get("/api/search/analytics?days=14"),
        "alerts": data.get("/api/alerts?page_size=6"),
        "activity": data.get("/api/audit?limit=12"),
        "analysis": data.get("/api/impact-matrix/latest"),
        "rules": {
            "total_rules": rules.get("total_rules"),
            "valid_rules": rules.get("valid_rules"),
            "regulators": rules.get("regulators"),
            "rule_sets": len(rules.get("rule_sets", [])),
        }
        if rules
        else None,
        "errors": errors,
    }


@app.get("/api/system/status", tags=["System"], summary="Health of every service, Elasticsearch, PostgreSQL, rules and import")
async def system_status(request: Request) -> dict[str, Any]:
    client: httpx.AsyncClient = request.app.state.client
    names = list(SERVICE_URLS)
    health_calls = await asyncio.gather(*(_get(client, n, "/health") for n in names))
    extra = await asyncio.gather(
        _get(client, "ingestion", "/api/imports/latest"),
        _get(client, "search", "/internal/stats", internal=True),
    )
    services = []
    for name, (_, payload, err, ms) in zip(names, health_calls, strict=True):
        services.append(
            {
                "name": name,
                "url": SERVICE_URLS[name],
                "reachable": err is None,
                "status": (payload or {}).get("status", "unreachable"),
                "latency_ms": round(ms, 1),
                "checks": (payload or {}).get("checks", {}),
                "error": err,
            }
        )
    by_name = {s["name"]: s for s in services}
    es_check = by_name.get("search", {}).get("checks", {}).get("elasticsearch", {"ok": False, "detail": "search service unreachable"})
    db_checks = [s["checks"].get("database") for s in services if s["checks"].get("database")]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": "ok" if all(s["status"] == "ok" for s in services) else "degraded",
        "gateway": {"status": "ok", "api_token_required": bool(get_settings().api_token)},
        "services": services,
        "elasticsearch": es_check,
        "postgresql": {
            "ok": bool(db_checks) and all(c["ok"] for c in db_checks),
            "detail": db_checks[0]["detail"] if db_checks else "no service reported",
        },
        "rules": by_name.get("rules", {}).get("checks", {}).get("rules"),
        "import": extra[0][1],
        "index": extra[1][1],
        "links": {"swagger_ui": "/api/docs", "openapi": "/api/openapi.json"},
    }


# ----------------------------------------------------------------------------- proxy


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"], include_in_schema=False)
async def proxy(path: str, request: Request) -> Response:
    full_path = f"/api/{path}"
    service = service_for(full_path)
    if service is None:
        return JSONResponse(status_code=404, content=error_body("not_found", f"No API route for {full_path}"))
    token = get_settings().api_token
    if token and requires_token(request.method, full_path):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {token}"):
            return JSONResponse(status_code=401, content=error_body("unauthorized", "A valid Bearer token is required for this operation"))
    client: httpx.AsyncClient = request.app.state.client
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP | {"content-length", "x-internal-token"}}
    headers["x-request-id"] = getattr(request.state, "request_id", "")
    body = await request.body()
    upstream = client.build_request(
        request.method,
        f"{SERVICE_URLS[service]}{full_path}",
        params=request.query_params.multi_items(),
        headers=headers,
        content=body,
    )
    try:
        r = await client.send(upstream, stream=True)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=503,
            content=error_body("service_unavailable", f"The {service} service is not reachable ({type(exc).__name__})"),
        )
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in HOP_BY_HOP}
    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=resp_headers, background=BackgroundTask(r.aclose))
