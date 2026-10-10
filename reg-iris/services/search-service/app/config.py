from functools import lru_cache
from typing import Literal

from iris_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "search-service"
    database_url: str = "postgresql+psycopg://iris:iris@localhost:5432/iris_search"

    search_backend: Literal["elasticsearch", "memory"] = "elasticsearch"
    elasticsearch_url: str = "http://localhost:9200"
    clause_index_alias: str = "iris-clauses"

    ingestion_url: str = "http://localhost:8001"  # service-to-service base URL

    enable_semantic: bool = False
    chroma_url: str = "http://localhost:8000"
    chroma_collection: str = "iris-clauses"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
