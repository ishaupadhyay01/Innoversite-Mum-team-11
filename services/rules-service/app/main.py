"""Rules & Impact Engine service: JSON rule engine, Impact Matrix, gap analysis, checklist."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from iris_shared.config import get_settings
from iris_shared.db import check_database
from iris_shared.logs import configure_logging
from iris_shared.web import install_error_handlers

from .api.routes import analysis_router, impact_router, rules_router, trades_router
from .registry import Registry


def build_registry() -> Registry:
    settings = get_settings()
    registry = Registry(
        rules_dir=settings.rules_dir,
        trades_dir=settings.trades_dir,
        schema_path=settings.schema_file,
        overlay_path=settings.config_dir / "rules_overlay.json",
    )
    registry.reload()
    return registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging("rules", get_settings().log_level)
    if not hasattr(app.state, "registry"):
        app.state.registry = build_registry()
    yield


app = FastAPI(
    title="Reg IRIS — Rules & Impact Engine Service",
    version="1.0.0",
    description="Generic JSON rule interpreter (no eval, no hard-coded rule logic), Impact Matrix, gap analysis and compliance checklist.",
    lifespan=lifespan,
)
install_error_handlers(app)
app.include_router(rules_router)
app.include_router(impact_router)
app.include_router(analysis_router)
app.include_router(trades_router)


@app.get("/health", tags=["System"], summary="Service health: database and rule configuration")
def health(request: Request) -> dict[str, object]:
    db_ok, db_detail = check_database()
    registry: Registry = request.app.state.registry
    rules_ok = bool(registry.all_rules) and all(r.valid for r in registry.all_rules) and not registry.load_errors
    return {
        "service": "rules",
        "status": "ok" if db_ok and rules_ok else "degraded",
        "checks": {
            "database": {"ok": db_ok, "detail": db_detail},
            "rules": {
                "ok": rules_ok,
                "detail": f"{len(registry.all_rules)} rule(s) in {len(registry.rule_sets)} file(s)"
                + (f"; errors: {registry.load_errors}" if registry.load_errors else ""),
            },
            "schema": {"ok": registry.schema is not None, "detail": registry.schema.source if registry.schema else "not loaded"},
            "datasets": {"ok": bool(registry.datasets()), "detail": ", ".join(p.name for p in registry.datasets())},
        },
    }
