"""Compare ANY two versions — two versions of one regulation, or two different regulations."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models import Comparison
from iris_common.diff import ClauseInput, diff_clauses
from iris_common.http import ServiceClient


def _load(ingestion: ServiceClient, version_id: uuid.UUID) -> tuple[str, list[ClauseInput]]:
    p = ingestion.get(f"/internal/v1/versions/{version_id}/index-payload")
    label = f"{p['regulator']} — {p['title']} ({p['version_label']})"
    return label, [
        ClauseInput(c["clause_ref"], c["text"], c.get("title"), c["page_start"], c["id"]) for c in p["clauses"]
    ]


def compare_versions(
    db: Session, ingestion: ServiceClient, left: uuid.UUID, right: uuid.UUID, include_unchanged: bool
) -> Comparison:
    left_label, left_clauses = _load(ingestion, left)
    right_label, right_clauses = _load(ingestion, right)
    result = diff_clauses(left_clauses, right_clauses, include_unchanged=include_unchanged)
    changes = []
    for c in result.changes:
        d = asdict(c)
        d["change"] = c.change.value
        changes.append(d)
    record = Comparison(
        left_version_id=left,
        right_version_id=right,
        left_label=left_label,
        right_label=right_label,
        summary=result.summary,
        changes=changes,
    )
    db.add(record)
    db.commit()
    return record
