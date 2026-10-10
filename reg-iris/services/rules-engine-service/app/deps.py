from __future__ import annotations

from functools import lru_cache

from fastapi import Header

from app.config import get_settings
from app.publisher import CeleryPublisher, EventPublisher
from app.storage import FileStorage, LocalFileStorage
from app.trades.schema import ReportingSchema, load_schema
from iris_common.http import ServiceClient


@lru_cache
def _storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_dir)


def get_storage() -> FileStorage:
    return _storage()


def get_publisher() -> EventPublisher:
    return CeleryPublisher()


def get_schema() -> ReportingSchema:
    return load_schema(get_settings().reporting_schema_path)


@lru_cache
def get_search_client() -> ServiceClient:
    s = get_settings()
    return ServiceClient(s.search_url, token=s.api_token, retries=1, timeout=5)


def get_actor(x_user: str | None = Header(default=None)) -> str | None:
    return x_user
