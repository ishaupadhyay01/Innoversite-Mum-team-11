"""Initial schema for Reg IRIS.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-10

CI runs a drift check (tests/test_migrations.py) that compares this migration
with the SQLAlchemy models, so the two cannot silently diverge.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _bigint_pk() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "regulatory_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_key", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("regulator", sa.String(100), nullable=False),
        sa.Column("jurisdiction", sa.String(50)),
        sa.Column("category", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("family_key"),
    )
    op.create_index("ix_regulatory_documents_regulator", "regulatory_documents", ["regulator"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_label", sa.String(50), nullable=False),
        sa.Column("version_seq", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(10), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("source_metadata_id", sa.Integer()),
        sa.Column("is_latest", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_detail", sa.Text()),
        sa.Column("title", sa.String(300)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("paragraph_count", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(30)),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("metadata_notes", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "version_label", name="uq_version_label"),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_version_content"),
        sa.UniqueConstraint("document_id", "version_seq", name="uq_version_seq"),
    )
    op.create_index("ix_versions_latest", "document_versions", ["document_id", "is_latest"])

    op.create_table(
        "document_paragraphs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section_heading", sa.String(500)),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("line_start", sa.Integer()),
        sa.Column("line_end", sa.Integer()),
        sa.Column("anchor", sa.String(200)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_paragraph_ordinal"),
    )
    op.create_index("ix_document_paragraphs_version_id", "document_paragraphs", ["version_id"])
    op.create_index("ix_document_paragraphs_content_hash", "document_paragraphs", ["content_hash"])

    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("regulatory_documents.id", ondelete="SET NULL")),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "regulatory_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("change_types", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("regulator", sa.String(100), nullable=False),
        sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("previous_version_label", sa.String(50)),
        sa.Column("new_version_label", sa.String(50), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("diff_stats", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", name="uq_alert_version"),
    )
    op.create_index("ix_regulatory_alerts_is_read", "regulatory_alerts", ["is_read"])
    op.create_index("ix_regulatory_alerts_event_time", "regulatory_alerts", ["event_time"])

    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("files_total", sa.Integer(), nullable=False),
        sa.Column("files_processed", sa.Integer(), nullable=False),
        sa.Column("files_skipped", sa.Integer(), nullable=False),
        sa.Column("files_failed", sa.Integer(), nullable=False),
        sa.Column("log", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
    )

    op.create_table(
        "search_history",
        sa.Column("id", _bigint_pk(), primary_key=True),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("normalized_query", sa.String(500), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("total_hits", sa.Integer(), nullable=False),
        sa.Column("took_ms", sa.Float(), nullable=False),
        sa.Column("relaxed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_search_history_normalized_query", "search_history", ["normalized_query"])
    op.create_index("ix_search_history_created_at", "search_history", ["created_at"])

    op.create_table(
        "rule_set_loads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("regulator", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("rule_count", sa.Integer(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_set_loads_file_name", "rule_set_loads", ["file_name"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("dataset", sa.String(255), nullable=False),
        sa.Column("dataset_hash", sa.String(64)),
        sa.Column("regulators", sa.JSON(), nullable=False),
        sa.Column("rule_ids", sa.JSON(), nullable=False),
        sa.Column("rules_snapshot", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("related_clauses", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Float()),
    )

    op.create_table(
        "impact_results",
        sa.Column("id", _bigint_pk(), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.String(64), nullable=False),
        sa.Column("asset_class", sa.String(50)),
        sa.Column("regulator", sa.String(100), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("rule_description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("affected_fields", sa.JSON(), nullable=False),
        sa.Column("actual_values", sa.JSON(), nullable=False),
        sa.Column("expected_condition", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("rule_source", sa.String(300), nullable=False),
        sa.Column("severity", sa.String(30)),
        sa.Column("category", sa.String(40)),
        sa.Column("conditional", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_impact_analysis_status", "impact_results", ["analysis_id", "status"])
    op.create_index("ix_impact_analysis_trade", "impact_results", ["analysis_id", "trade_id"])
    op.create_index("ix_impact_analysis_rule", "impact_results", ["analysis_id", "rule_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", _bigint_pk(), primary_key=True),
        sa.Column("service", sa.String(30), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(40)),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    for table in (
        "audit_events",
        "impact_results",
        "analysis_runs",
        "rule_set_loads",
        "search_history",
        "import_runs",
        "regulatory_alerts",
        "upload_jobs",
        "document_paragraphs",
        "document_versions",
        "regulatory_documents",
    ):
        op.drop_table(table)
