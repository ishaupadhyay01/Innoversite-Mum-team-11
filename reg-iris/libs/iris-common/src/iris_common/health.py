"""Liveness / readiness endpoints used by Docker healthchecks and the gateway."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

ReadinessCheck = Callable[[], Awaitable[bool] | bool]


def health_router(service_name: str, version: str, checks: dict[str, ReadinessCheck] | None = None) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])
    checks = checks or {}

    @router.get("/live", summary="Liveness probe")
    async def live() -> dict[str, str]:
        return {"status": "ok", "service": service_name, "version": version}

    @router.get("/ready", summary="Readiness probe (checks dependencies)")
    async def ready() -> JSONResponse:
        results: dict[str, str] = {}
        healthy = True
        for name, check in checks.items():
            try:
                outcome = check()
                if hasattr(outcome, "__await__"):
                    outcome = await outcome  # type: ignore[misc]
                results[name] = "ok" if outcome else "down"
                healthy &= bool(outcome)
            except Exception as exc:  # noqa: BLE001 - readiness must never raise
                results[name] = f"down: {exc.__class__.__name__}"
                healthy = False
        return JSONResponse(
            {"status": "ok" if healthy else "degraded", "checks": results}, status_code=200 if healthy else 503
        )

    return router
