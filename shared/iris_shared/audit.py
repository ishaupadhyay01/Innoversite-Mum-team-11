"""Append-only audit trail helper."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent

logger = logging.getLogger("iris.audit")


def record(
    session: Session,
    service: str,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session (committed with the caller's transaction)."""
    session.add(
        AuditEvent(
            service=service,
            action=action,
            summary=summary[:500],
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail or {},
        )
    )
    logger.info(summary, extra={"action": action, "entity_type": entity_type, "entity_id": entity_id})
