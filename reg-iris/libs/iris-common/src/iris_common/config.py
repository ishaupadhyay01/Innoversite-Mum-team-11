"""Environment-driven configuration shared by all services.

Every service subclasses :class:`BaseServiceSettings` and adds its own fields.
Values come from environment variables (or a local ``.env`` file in development);
nothing secret is ever hard-coded.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "reg-iris-service"
    environment: Literal["local", "test", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # Optional static bearer token. Empty = auth disabled (local/demo only).
    api_token: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])

    max_upload_mb: int = 50


@lru_cache
def cached_settings(cls: type[BaseServiceSettings]) -> BaseServiceSettings:
    return cls()
