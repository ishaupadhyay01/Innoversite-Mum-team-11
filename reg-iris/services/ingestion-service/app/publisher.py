"""Outbound async events (Celery tasks sent by name). Overridden by a fake in tests."""

from __future__ import annotations

import logging
from typing import Any, Protocol

log = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def send(self, task_name: str, **kwargs: Any) -> None: ...


class CeleryPublisher:
    def send(self, task_name: str, **kwargs: Any) -> None:
        from app.celery_app import celery_app

        log.info("task_sent", extra={"task": task_name, "task_kwargs": kwargs})
        celery_app.send_task(task_name, kwargs=kwargs)
