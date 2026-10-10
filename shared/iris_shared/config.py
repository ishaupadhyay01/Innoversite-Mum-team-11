"""Environment-driven configuration shared by all services.

All values come from environment variables (see ``.env.example``). No
credentials are hard-coded; the defaults below are only paths, ports and
service hostnames for the Docker Compose network.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    service_name: str = Field(default="reg-iris", alias="SERVICE_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(alias="DATABASE_URL")
    elasticsearch_url: str = Field(default="http://elasticsearch:9200", alias="ELASTICSEARCH_URL")
    es_index_alias: str = Field(default="reg-iris-paragraphs", alias="ES_INDEX_ALIAS")

    # Shared secret for service-to-service calls on /internal/* routes.
    internal_token: str = Field(alias="INTERNAL_TOKEN", min_length=8)
    # Optional static bearer token protecting mutating public endpoints at the gateway.
    api_token: str | None = Field(default=None, alias="API_TOKEN")

    ingestion_url: str = Field(default="http://ingestion:8001", alias="INGESTION_URL")
    search_url: str = Field(default="http://search:8002", alias="SEARCH_URL")
    rules_url: str = Field(default="http://rules:8003", alias="RULES_URL")

    dataset_dir: Path = Field(default=Path("/data/dataset"), alias="DATASET_DIR")
    upload_dir: Path = Field(default=Path("/data/uploads"), alias="UPLOAD_DIR")
    config_dir: Path = Field(default=Path("/config"), alias="CONFIG_DIR")

    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB", ge=1, le=200)
    seed_on_startup: bool = Field(default=True, alias="SEED_ON_STARTUP")
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def regulations_dir(self) -> Path:
        return self.dataset_dir / "regulations"

    @property
    def metadata_file(self) -> Path:
        return self.dataset_dir / "metadata" / "doc_metadata.csv"

    @property
    def rules_dir(self) -> Path:
        return self.dataset_dir / "rules"

    @property
    def trades_dir(self) -> Path:
        return self.dataset_dir / "trades"

    @property
    def schema_file(self) -> Path:
        return self.dataset_dir / "schema" / "reporting_schema.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
