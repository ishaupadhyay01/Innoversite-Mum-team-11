"""Search & Comparison Service (Module 2).  Swagger UI: /docs"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app import __version__
from app.api.v1 import public_routers
from app.config import get_settings
from app.db import get_engine
from app.deps import get_keyword_backend
from iris_common.app_factory import create_app

log = logging.getLogger(__name__)


def _db_ready() -> bool:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


def _search_ready() -> bool:
    return get_keyword_backend().ping()


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    try:
        get_keyword_backend().ensure_index()
    except Exception:  # noqa: BLE001 - ES may still be starting; indexer retries, readiness reports it
        log.warning("search_index_not_ready_at_startup")
    yield


app = create_app(
    settings=get_settings(),
    title="Reg IRIS — Search & Comparison Service",
    description="Keyword (Elasticsearch) and optional semantic (ChromaDB) clause search with exact citations, "
    "plus clause-level comparison of any two document versions or regulations.",
    version=__version__,
    routers=public_routers,
    readiness_checks={"database": _db_ready, "search_backend": _search_ready},
    lifespan=lifespan,
)
