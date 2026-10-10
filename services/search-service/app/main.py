"""Search & Retrieval service: Elasticsearch BM25 keyword search with citations."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from elasticsearch import Elasticsearch
from fastapi import FastAPI, Request

from iris_shared.config import get_settings
from iris_shared.db import check_database
from iris_shared.logs import configure_logging
from iris_shared.web import install_error_handlers

from .api.routes import internal, public
from .indexing.indexer import Indexer
from .search.service import SearchService, load_noise_words

logger = logging.getLogger("search")


def _ensure_index_with_retry(indexer: Indexer, attempts: int = 60) -> None:
    delay = 1.0
    for i in range(attempts):
        try:
            created = indexer.ensure_index()
            # "created" is a reserved LogRecord attribute; using it in extra= raises KeyError and loops start-up.
            logger.info("index ready", extra={"index_created": created, "index": indexer.concrete_name})
            return
        except Exception as exc:  # noqa: BLE001 - ES may still be starting
            logger.warning("waiting for Elasticsearch (%s/%s): %s: %s", i + 1, attempts, type(exc).__name__, exc)
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)
    logger.error("Elasticsearch not reachable; search endpoints will return 503 until it is")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("search", settings.log_level)
    es = Elasticsearch(settings.elasticsearch_url, request_timeout=30, retry_on_timeout=True, max_retries=2)
    indexer = Indexer(es, settings.es_index_alias, settings.config_dir / "synonyms.txt")
    app.state.es = es
    app.state.indexer = indexer
    app.state.search_service = SearchService(es, settings.es_index_alias, load_noise_words(settings.config_dir / "query_noise_words.txt"))
    threading.Thread(target=_ensure_index_with_retry, args=(indexer,), daemon=True).start()
    yield
    es.close()


app = FastAPI(
    title="Reg IRIS — Search & Retrieval Service",
    version="1.0.0",
    description="Keyword search (Elasticsearch BM25) over regulatory paragraphs with filters, highlighting and exact citations. No vector search, no LLM.",
    lifespan=lifespan,
)
install_error_handlers(app)
app.include_router(public)
app.include_router(internal)


@app.get("/health", tags=["System"], summary="Service health with Elasticsearch and database checks")
def health(request: Request) -> dict[str, object]:
    db_ok, db_detail = check_database()
    es: Elasticsearch = request.app.state.es
    indexer: Indexer = request.app.state.indexer
    try:
        info = es.cluster.health(timeout="2s")
        es_ok = info["status"] in {"green", "yellow"} and bool(es.indices.exists_alias(name=indexer.alias))
        es_detail = f"cluster {info['status']}" + ("" if es_ok else "; index not created yet")
    except Exception as exc:  # noqa: BLE001
        es_ok, es_detail = False, f"{type(exc).__name__}"
    return {
        "service": "search",
        "status": "ok" if (db_ok and es_ok) else "degraded",
        "checks": {
            "elasticsearch": {"ok": es_ok, "detail": es_detail},
            "database": {"ok": db_ok, "detail": db_detail},
        },
    }
