from functools import lru_cache

from iris_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "rules-engine-service"
    database_url: str = "postgresql+psycopg://iris:iris@localhost:5432/iris_rules"
    storage_dir: str = "/data/rules-engine"
    reporting_schema_path: str | None = None  # default: bundled app/trades/reporting_schema.json

    # Batch processing
    chunk_size: int = 5_000  # rows evaluated + inserted per DB transaction
    fanout_threshold_rows: int = 50_000  # above this, chunks are evaluated in parallel Celery tasks
    insert_batch_size: int = 5_000

    # Traceability: auto-link rules to clauses via search-service
    search_url: str = "http://localhost:8002"
    auto_link_clauses: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
