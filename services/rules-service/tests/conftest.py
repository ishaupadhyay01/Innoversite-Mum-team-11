"""Shared fixtures. Environment defaults are set before any app module is imported."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SERVICE = Path(__file__).resolve().parents[1]
for p in (str(SERVICE), str(REPO / "shared")):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("INTERNAL_TOKEN", "test-internal-token")

os.environ.setdefault("DATASET_DIR", str(REPO / "data"))
os.environ.setdefault("CONFIG_DIR", str(REPO / "config"))

CONFIG = REPO / "config"

DATA = REPO / "data"

import pytest  # noqa: E402

from app.engine import Overlay, load_rule_sets  # noqa: E402
from app.engine.dataset import ReportingSchema, load_trades  # noqa: E402


@pytest.fixture(scope="session")
def schema() -> ReportingSchema:
    return ReportingSchema.load(DATA / "schema" / "reporting_schema.json")


@pytest.fixture(scope="session")
def rules(schema: ReportingSchema):  # type: ignore[no-untyped-def]
    sets = load_rule_sets(DATA / "rules", schema.field_names, Overlay.load(CONFIG / "rules_overlay.json"))
    return {r.id: r for rs in sets for r in rs.rules}


@pytest.fixture(scope="session")
def dataset(schema: ReportingSchema):  # type: ignore[no-untyped-def]
    return load_trades(DATA / "trades" / "sample_trades.csv", schema)
