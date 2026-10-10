"""Ingestion service: uploads, parsing, versioning, diffs and What's New alerts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from iris_shared.config import get_settings
from iris_shared.logs import configure_logging
from iris_shared.web import install_error_handlers

from .api import alerts, documents, system
from .services.seeding import start_background_seed


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log = configure_logging("ingestion", settings.log_level)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.seed_on_startup:
        log.info("starting background dataset import")
        start_background_seed()
    yield


app = FastAPI(
    title="Reg IRIS — Ingestion Service",
    version="1.0.0",
    description="Document upload and extraction, version history, deterministic version comparison and What's New alerts.",
    lifespan=lifespan,
)
install_error_handlers(app)
app.include_router(documents.router)
app.include_router(alerts.router)
app.include_router(system.router)
