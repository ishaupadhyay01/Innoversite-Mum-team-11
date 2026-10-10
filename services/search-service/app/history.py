"""Search history recording and analytics (PostgreSQL)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from iris_shared.db import session_scope
from iris_shared.models import SearchHistory

logger = logging.getLogger("search.history")


def normalize_query(q: str) -> str:
    return " ".join(q.lower().split())[:500]


def record_search(query: str, filters: dict[str, Any], scope: str, total: int, took_ms: float, relaxed: bool) -> None:
    if not query.strip():
        return
    try:
        with session_scope() as s:
            s.add(
                SearchHistory(
                    query=query[:500],
                    normalized_query=normalize_query(query),
                    filters=filters,
                    scope=scope,
                    total_hits=total,
                    took_ms=took_ms,
                    relaxed=relaxed,
                )
            )
    except Exception:
        logger.exception("failed to record search history")


def history_suggestions(session: Session, prefix: str, limit: int = 4) -> list[str]:
    norm = normalize_query(prefix)
    if len(norm) < 2:
        return []
    rows = session.execute(
        select(SearchHistory.normalized_query, func.count().label("n"))
        .where(SearchHistory.normalized_query.like(f"{norm}%"), SearchHistory.total_hits > 0)
        .group_by(SearchHistory.normalized_query)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def analytics(session: Session, days: int = 14) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    total = session.scalar(select(func.count(SearchHistory.id))) or 0
    recent = select(SearchHistory).where(SearchHistory.created_at >= since).subquery()
    avg_ms = session.scalar(select(func.avg(recent.c.took_ms)))
    zero = session.scalar(select(func.count()).select_from(recent).where(recent.c.total_hits == 0)) or 0
    recent_count = session.scalar(select(func.count()).select_from(recent)) or 0
    top = session.execute(
        select(recent.c.normalized_query, func.count().label("n"), func.avg(recent.c.total_hits).label("hits"))
        .group_by(recent.c.normalized_query)
        .order_by(func.count().desc())
        .limit(8)
    ).all()
    zero_queries = session.execute(
        select(recent.c.normalized_query, func.count().label("n"))
        .where(recent.c.total_hits == 0)
        .group_by(recent.c.normalized_query)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    day = func.date(recent.c.created_at)
    per_day = session.execute(
        select(day.label("day"), func.count().label("n"), cast(func.avg(recent.c.took_ms), Integer).label("ms")).group_by(day).order_by(day)
    ).all()
    return {
        "total_searches": total,
        "window_days": days,
        "searches_in_window": recent_count,
        "avg_response_ms": round(float(avg_ms), 1) if avg_ms is not None else None,
        "zero_result_rate": round(zero / recent_count, 3) if recent_count else None,
        "top_queries": [{"query": q, "count": n, "avg_hits": round(float(h or 0), 1)} for q, n, h in top],
        "zero_result_queries": [{"query": q, "count": n} for q, n in zero_queries],
        "per_day": [{"day": str(d), "searches": n, "avg_ms": ms} for d, n, ms in per_day],
    }


def recent_queries(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    rows = session.scalars(select(SearchHistory).order_by(SearchHistory.created_at.desc()).limit(limit)).all()
    return [
        {"query": r.query, "total_hits": r.total_hits, "took_ms": r.took_ms, "scope": r.scope, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
