"""Single place that wires a FastAPI app the same way for every service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import bearer_guard
from .config import BaseServiceSettings
from .errors import register_exception_handlers
from .health import ReadinessCheck, health_router
from .logging import configure_logging
from .middleware import RequestContextMiddleware


def create_app(
    *,
    settings: BaseServiceSettings,
    title: str,
    description: str,
    version: str,
    routers: Sequence[APIRouter],
    internal_routers: Sequence[APIRouter] = (),
    readiness_checks: dict[str, ReadinessCheck] | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
    openapi_tags: list[dict[str, str]] | None = None,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level, settings.log_json)
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        openapi_tags=openapi_tags,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    register_exception_handlers(app)

    guard = Depends(bearer_guard(lambda: settings.api_token))
    for router in routers:
        app.include_router(router, dependencies=[guard])
    # Internal (service-to-service) routes: not exposed by the gateway.
    for router in internal_routers:
        app.include_router(router, dependencies=[guard])
    app.include_router(health_router(settings.service_name, version, readiness_checks))
    return app
