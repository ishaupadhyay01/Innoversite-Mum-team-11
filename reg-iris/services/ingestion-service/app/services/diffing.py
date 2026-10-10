"""Version comparison + What's New card generation."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, CardType, DocumentVersion, VersionDiff, WhatsNewCard
from app.services.versioning import get_version
from iris_common.diff import ChangeType, ClauseInput, DiffResult, diff_clauses
from iris_common.errors import NotFoundError, ValidationFailedError


def _inputs(version: DocumentVersion) -> list[ClauseInput]:
    return [ClauseInput(c.clause_ref, c.text, c.title, c.page_start, str(c.id)) for c in version.clauses]


def compute_diff(old: DocumentVersion, new: DocumentVersion) -> DiffResult:
    return diff_clauses(_inputs(old), _inputs(new))


def previous_version(db: Session, version: DocumentVersion) -> DocumentVersion | None:
    if version.parent_version_id:
        return db.get(DocumentVersion, version.parent_version_id)
    return db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == version.document_id, DocumentVersion.version_number < version.version_number
        )
        .order_by(DocumentVersion.version_number.desc())
    )


def get_or_create_diff(db: Session, from_id: uuid.UUID, to_id: uuid.UUID) -> tuple[VersionDiff, DiffResult]:
    old, new = get_version(db, from_id), get_version(db, to_id)
    if old.document_id != new.document_id:
        raise ValidationFailedError("Versions belong to different documents; use search-service /compare instead")
    result = compute_diff(old, new)
    existing = db.scalar(
        select(VersionDiff).where(VersionDiff.from_version_id == from_id, VersionDiff.to_version_id == to_id)
    )
    if existing:
        return existing, result
    record = VersionDiff(
        document_id=new.document_id,
        from_version_id=from_id,
        to_version_id=to_id,
        summary=result.summary,
        changes=[_change_dict(c) for c in result.changes],
    )
    db.add(record)
    db.flush()
    return record, result


def _change_dict(change) -> dict:  # type: ignore[no-untyped-def]
    d = asdict(change)
    d["change"] = change.change.value
    return d


def generate_whats_new(db: Session, version: DocumentVersion) -> WhatsNewCard:
    doc = version.document
    prev = previous_version(db, version)
    if prev is None or not prev.clauses:
        card = WhatsNewCard(
            card_type=CardType.NEW_DOCUMENT.value,
            document_id=doc.id,
            version_id=version.id,
            regulator=doc.regulator,
            title=doc.title,
            effective_date=version.effective_date,
            headline=f"New {doc.regulator} document published with {version.clause_count or 0} clauses.",
            summary={"ADDED": version.clause_count or 0, "REMOVED": 0, "MODIFIED": 0},
            highlights=[
                {"clause_ref": c.clause_ref, "title": c.title, "change": "ADDED", "page": c.page_start}
                for c in version.clauses[:3]
            ],
        )
    else:
        diff, result = get_or_create_diff(db, prev.id, version.id)
        changed = [c for c in result.changes if c.change is not ChangeType.UNCHANGED]
        card = WhatsNewCard(
            card_type=CardType.NEW_VERSION.value,
            document_id=doc.id,
            version_id=version.id,
            diff_id=diff.id,
            regulator=doc.regulator,
            title=doc.title,
            effective_date=version.effective_date,
            headline=f"{prev.version_label} → {version.version_label}: {result.headline()}",
            summary=result.summary,
            highlights=[
                {
                    "clause_ref": c.clause_ref,
                    "title": c.title,
                    "change": c.change.value,
                    "page": c.new_page or c.old_page,
                    "excerpt": (c.new_text or c.old_text or "")[:240],
                }
                for c in changed[:5]
            ],
        )
    db.add(card)
    db.flush()
    db.add(Alert(card_id=card.id, message=f"{doc.regulator}: {card.headline}"))
    return card


def require_card(db: Session, card_id: uuid.UUID) -> WhatsNewCard:
    card = db.get(WhatsNewCard, card_id)
    if card is None:
        raise NotFoundError(f"What's New card {card_id} not found")
    return card
