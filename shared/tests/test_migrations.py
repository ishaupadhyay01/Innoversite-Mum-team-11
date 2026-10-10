"""Migration drift check: the Alembic migration must produce exactly the SQLAlchemy models.

Runs against PostgreSQL when TEST_POSTGRES_URL is set (CI service container).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PG_URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set")


def test_migration_matches_models() -> None:
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, text

    from iris_shared.models import Base

    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    os.environ["DATABASE_URL"] = PG_URL
    cfg = Config(str(Path(__file__).resolve().parents[1] / "iris_shared" / "migrations" / "alembic.ini"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"migration and models differ: {diff}"
    command.downgrade(cfg, "base")
