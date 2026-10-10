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
os.environ.setdefault("SEED_ON_STARTUP", "false")
os.environ.setdefault("DATASET_DIR", str(REPO / "data"))
os.environ.setdefault("CONFIG_DIR", str(REPO / "config"))

import pytest  # noqa: E402

DATA = REPO / "data"
REGULATIONS = DATA / "regulations"


@pytest.fixture
def regulations() -> Path:
    return REGULATIONS
