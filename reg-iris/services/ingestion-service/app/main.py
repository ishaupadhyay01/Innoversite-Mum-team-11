"""Ingestion & Versioning Service (Module 1).  Swagger UI: /docs"""

from sqlalchemy import text

from app import __version__
from app.api.v1 import internal_routers, public_routers
from app.config import get_settings
from app.db import get_engine
from iris_common.app_factory import create_app


def _db_ready() -> bool:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


app = create_app(
    settings=get_settings(),
    title="Reg IRIS — Ingestion & Versioning Service",
    description=(
        "Upload regulatory documents (PDF/HTML/TXT), detect duplicates, suggest matches, "
        "manage ACTIVE/INACTIVE versions, compare versions and publish What's New alerts."
    ),
    version=__version__,
    routers=public_routers,
    internal_routers=internal_routers,
    readiness_checks={"database": _db_ready},
)
