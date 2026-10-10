"""Ingestion-service persistence model (database: iris_ingestion).

documents 1──* document_versions 1──* document_pages
                         │  1──* clauses
documents 1──* version_diffs (from_version → to_version)
documents 1──* whats_new_cards 1──* alerts
audit_log (append-only, any entity)

Invariant: at most ONE document_versions row per document has status = 'ACTIVE'
(enforced by the partial unique index uq_document_versions_one_active).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class VersionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ProcessingStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class CardType(StrEnum):
    NEW_DOCUMENT = "NEW_DOCUMENT"
    NEW_VERSION = "NEW_VERSION"


class Document(Base):
    """A logical regulation (e.g. 'MiFID II Trade Reporting'). Owns many versions."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    regulator: Mapped[str] = mapped_column(String(100), index=True)
    regulator_canonical: Mapped[str] = mapped_column(String(100), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(50), index=True)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", use_alter=True, name="fk_documents_active_version", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", foreign_keys="DocumentVersion.document_id", order_by="DocumentVersion.version_number"
    )
    active_version: Mapped[DocumentVersion | None] = relationship(foreign_keys=[active_version_id], post_update=True)


class DocumentVersion(Base):
    """One uploaded file = one immutable version of a Document."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_document_versions_status"),
        CheckConstraint(
            "processing_status IN ('UPLOADED','PROCESSING','READY','FAILED')", name="ck_document_versions_processing"
        ),
        Index(
            "uq_document_versions_one_active",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("document_versions.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(16), default=VersionStatus.INACTIVE.value, index=True)
    processing_status: Mapped[str] = mapped_column(String(16), default=ProcessingStatus.UPLOADED.value)
    activate_on_ready: Mapped[bool] = mapped_column(Boolean, default=True)

    original_filename: Mapped[str] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)  # exact-duplicate detection
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)

    page_count: Mapped[int | None] = mapped_column(Integer)
    clause_count: Mapped[int | None] = mapped_column(Integer)
    fingerprint: Mapped[list[int] | None] = mapped_column(JsonType)  # MinHash for similarity
    quality_warnings: Mapped[list[str] | None] = mapped_column(JsonType)
    error_message: Mapped[str | None] = mapped_column(Text)

    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])
    clauses: Mapped[list[Clause]] = relationship(
        back_populates="version", order_by="Clause.ordinal", cascade="all, delete-orphan"
    )
    pages: Mapped[list[DocumentPage]] = relationship(order_by="DocumentPage.page_number", cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("version_id", "page_number", name="uq_document_pages"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Clause(Base):
    """Smallest citable unit (paragraph / article / Q&A / HTML section)."""

    __tablename__ = "clauses"
    __table_args__ = (UniqueConstraint("version_id", "clause_ref", name="uq_clauses_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    clause_ref: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    anchor: Mapped[str | None] = mapped_column(String(200))  # HTML element id for deep links
    text_hash: Mapped[str] = mapped_column(String(64))

    version: Mapped[DocumentVersion] = relationship(back_populates="clauses")


class VersionDiff(Base):
    __tablename__ = "version_diffs"
    __table_args__ = (UniqueConstraint("from_version_id", "to_version_id", name="uq_version_diffs_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    from_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"))
    to_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"))
    summary: Mapped[dict[str, int]] = mapped_column(JsonType)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WhatsNewCard(Base):
    __tablename__ = "whats_new_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    card_type: Mapped[str] = mapped_column(String(20))
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"))
    diff_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("version_diffs.id", ondelete="SET NULL"))
    regulator: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(500))
    effective_date: Mapped[date | None] = mapped_column(Date)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[dict[str, int]] = mapped_column(JsonType, default=dict)
    highlights: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("whats_new_cards.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(10), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
