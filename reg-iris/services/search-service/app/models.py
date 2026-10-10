"""Search-service persistence (database: iris_search). Elasticsearch/Chroma hold the indexes;
Postgres keeps index bookkeeping, query analytics and saved comparisons."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class IndexedVersion(Base):
    __tablename__ = "indexed_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(16))
    clause_count: Mapped[int] = mapped_column(Integer, default=0)
    keyword_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    semantic_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SearchQueryLog(Base):
    __tablename__ = "search_query_log"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))
    filters: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    result_count: Mapped[int] = mapped_column(Integer)
    took_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    left_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    right_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    left_label: Mapped[str] = mapped_column(String(500))
    right_label: Mapped[str] = mapped_column(String(500))
    summary: Mapped[dict[str, int]] = mapped_column(JsonType)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
