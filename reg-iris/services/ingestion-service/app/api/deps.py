from functools import lru_cache

from fastapi import Header

from app.config import get_settings
from app.publisher import CeleryPublisher, EventPublisher
from app.storage import FileStorage, LocalFileStorage


@lru_cache
def _storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_dir)


def get_storage() -> FileStorage:
    return _storage()


def get_publisher() -> EventPublisher:
    return CeleryPublisher()


def get_actor(x_user: str | None = Header(default=None, description="Acting user (set by gateway/SSO)")) -> str | None:
    return x_user
