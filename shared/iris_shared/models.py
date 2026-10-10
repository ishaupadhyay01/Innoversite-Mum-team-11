"""Relational data model (PostgreSQL).

Ownership by service (all services share one database, each owns its tables):

* ingestion: regulatory_documents, document_versions, document_paragraphs,
  upload_jobs, regulatory_alerts, import_runs
* search:    search_history
* rules:     rule_set_loads, analysis_runs, impact_results
* all:       audit_events (append-only)

Full paragraph text lives in Elasticsearch only; ``document_paragraphs``
keeps the location metadata (page, heading, anchor, hash) that links
Document -> Version -> Paragraph -> Elasticsearch document id.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RegulatoryDocument(Base):
    """A document family: all versions of one regulation/guidance document."""

    __tablename__ = "regulatory_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    regulator: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(50))
    category: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", order_by="DocumentVersion.version_seq", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_label", name="uq_version_label"),
        UniqueConstraint("document_id", "content_hash", name="uq_version_content"),
        UniqueConstraint("document_id", "version_seq", name="uq_version_seq"),
        Index("ix_versions_latest", "document_id", "is_latest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_date: Mapped[date | None] = mapped_column(Date)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")  # seed | upload
    source_metadata_id: Mapped[int | None] = mapped_column(Integer)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    status_detail: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(300))
    page_count: Mapped[int | None] = mapped_column(Integer)
    paragraph_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extractor: Mapped[str | None] = mapped_column(String(30))
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[RegulatoryDocument] = relationship(back_populates="versions")
    paragraphs: Mapped[list[DocumentParagraph]] = relationship(
        back_populates="version", order_by="DocumentParagraph.ordinal", cascade="all, delete-orphan"
    )


class DocumentParagraph(Base):
    """Location metadata for one indexed paragraph; ``id`` is also the Elasticsearch _id."""

    __tablename__ = "document_paragraphs"
    __table_args__ = (UniqueConstraint("version_id", "ordinal", name="uq_paragraph_ordinal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    section_heading: Mapped[str | None] = mapped_column(String(500))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    anchor: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped[DocumentVersion] = relationship(back_populates="paragraphs")


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")  # queued|processing|indexed|failed
    detail: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="SET NULL"))
    version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RegulatoryAlert(Base):
    __tablename__ = "regulatory_alerts"
    __table_args__ = (UniqueConstraint("version_id", name="uq_alert_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    previous_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)  # New Document | New Version
    change_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_version_label: Mapped[str | None] = mapped_column(String(50))
    new_version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    diff_stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # initial_import | upload
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running|completed|completed_with_errors|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    files_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    log: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    total_hits: Mapped[int] = mapped_column(Integer, nullable=False)
    took_ms: Mapped[float] = mapped_column(Float, nullable=False)
    relaxed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class RuleSetLoad(Base):
    __tablename__ = "rule_set_loads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="impact")
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # queued|running|completed|failed
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_hash: Mapped[str | None] = mapped_column(String(64))
    regulators: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rule_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rules_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    related_clauses: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)


class ImpactResult(Base):
    __tablename__ = "impact_results"
    __table_args__ = (
        Index("ix_impact_analysis_status", "analysis_id", "status"),
        Index("ix_impact_analysis_trade", "analysis_id", "trade_id"),
        Index("ix_impact_analysis_rule", "analysis_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[str | None] = mapped_column(String(50))
    regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    actual_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expected_condition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    rule_source: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(30))
    category: Mapped[str | None] = mapped_column(String(40))
    conditional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    service: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
