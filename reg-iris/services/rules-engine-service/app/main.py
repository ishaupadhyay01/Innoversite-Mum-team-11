"""Rules & Impact Analysis Service (Module 3).  Swagger UI: /docs"""

from sqlalchemy import text

from app import __version__
from app.api.v1 import public_routers
from app.config import get_settings
from app.db import get_engine
from iris_common.app_factory import create_app


def _db_ready() -> bool:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


app = create_app(
    settings=get_settings(),
    title="Reg IRIS — Rules & Impact Analysis Service",
    description=(
        "Upload JSON rule sets and trade CSVs, run the JSONLogic rules engine in batches, and explore the "
        "Impact Matrix (trade ↔ rule) with explanations, statistics, filters, pagination and CSV export. "
        "Every FAIL is traceable to its rule and regulatory clause."
    ),
    version=__version__,
    routers=public_routers,
    readiness_checks={"database": _db_ready},
)
