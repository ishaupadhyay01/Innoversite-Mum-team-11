"""Rules-engine persistence model (database: iris_rules).

rule_sets 1──* rules 1──0..1 rule_clause_links      (traceability to a regulatory clause)
trade_datasets 1──* validation_runs 1──* validation_results   (the Impact Matrix)

A run snapshots the rules it used (validation_runs.rule_snapshot) so results stay reproducible and
auditable even after a rule set is replaced.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RuleSet(Base):
    __tablename__ = "rule_sets"
    __table_args__ = (
        UniqueConstraint("regulator_canonical", "version_number", name="uq_rule_sets_version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_rule_sets_status"),
        Index(
            "uq_rule_sets_one_active",
            "regulator_canonical",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    regulator: Mapped[str] = mapped_column(String(100))
    regulator_canonical: Mapped[str] = mapped_column(String(100), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(50))
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    source_filename: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JsonType)
    lint: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    rule_count: Mapped[int] = mapped_column(Integer)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # ingestion document (by reference)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    rules: Mapped[list[Rule]] = relationship(
        back_populates="rule_set", cascade="all, delete-orphan", order_by="Rule.ordinal"
    )


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("rule_set_id", "code", name="uq_rules_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rule_sets.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    logic: Mapped[Any] = mapped_column(JsonType)
    applies_when: Mapped[Any | None] = mapped_column(JsonType)
    impact: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="HIGH")
    fields: Mapped[list[str]] = mapped_column(JsonType, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    declared_clause_ref: Mapped[str | None] = mapped_column(String(100))  # from the JSON "source"

    rule_set: Mapped[RuleSet] = relationship(back_populates="rules")
    clause_link: Mapped[RuleClauseLink | None] = relationship(
        back_populates="rule", uselist=False, cascade="all, delete-orphan"
    )


class RuleClauseLink(Base):
    """Lineage: which regulatory clause (document + version + page) justifies this rule."""

    __tablename__ = "rule_clause_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rules.id", ondelete="CASCADE"), unique=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    clause_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    clause_ref: Mapped[str | None] = mapped_column(String(100))
    page: Mapped[int | None] = mapped_column(Integer)
    citation_label: Mapped[str | None] = mapped_column(String(500))
    file_url: Mapped[str | None] = mapped_column(String(500))
    excerpt: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(20))  # MANUAL | AUTO_SEARCH
    score: Mapped[float | None] = mapped_column(Float)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    rule: Mapped[Rule] = relationship(back_populates="clause_link")


class TradeDataset(Base):
    __tablename__ = "trade_datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24))  # VALID | VALID_WITH_WARNINGS | INVALID
    validation: Mapped[dict[str, Any]] = mapped_column(JsonType)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trade_datasets.id"), index=True)
    rule_set_ids: Mapped[list[str]] = mapped_column(JsonType)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # optional regulatory doc context
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED.value, index=True)
    rule_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_rules: Mapped[int] = mapped_column(Integer, default=0)
    chunks_total: Mapped[int] = mapped_column(Integer, default=0)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ValidationResult(Base):
    """One cell of the Impact Matrix: (trade × rule) → status + explanation + lineage."""

    __tablename__ = "validation_results"
    __table_args__ = (
        Index("ix_results_run_status", "run_id", "status"),
        Index("ix_results_run_trade", "run_id", "trade_id"),
        Index("ix_results_run_rule", "run_id", "rule_code"),
        CheckConstraint("status IN ('PASS','FAIL','NOT_APPLICABLE','ERROR')", name="ck_results_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("validation_runs.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    trade_id: Mapped[str | None] = mapped_column(String(64))
    asset_class: Mapped[str | None] = mapped_column(String(32))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rule_code: Mapped[str] = mapped_column(String(64))
    regulator: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text)
    field_values: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    clause_ref: Mapped[str | None] = mapped_column(String(100))
    citation_label: Mapped[str | None] = mapped_column(String(500))
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
