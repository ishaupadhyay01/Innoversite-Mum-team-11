from functools import lru_cache

from iris_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ingestion-service"
    database_url: str = "postgresql+psycopg://iris:iris@localhost:5432/iris_ingestion"
    storage_dir: str = "/data/regulations"
    allowed_extensions: list[str] = ["pdf", "html", "htm", "txt"]

    # Match-suggestion tuning
    match_min_score: float = 0.30
    match_new_version_score: float = 0.60
    match_max_results: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
