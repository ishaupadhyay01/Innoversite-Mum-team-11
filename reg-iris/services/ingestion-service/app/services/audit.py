from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from iris_common.logging import request_id_ctx


def record(
    db: Session, entity_type: str, entity_id: object, action: str, actor: str | None = None, **payload: Any
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor=actor,
            payload={
                k: str(v) if not isinstance(v, (int, float, bool, type(None), list, dict)) else v
                for k, v in payload.items()
            },
            request_id=request_id_ctx.get(),
        )
    )
