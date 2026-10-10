from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ResultStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE", "ERROR"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LintIssueOut(BaseModel):
    level: str
    rule_code: str | None
    message: str


class ClauseLinkOut(ORM):
    document_id: uuid.UUID | None
    version_id: uuid.UUID | None
    clause_id: uuid.UUID | None
    clause_ref: str | None
    page: int | None
    citation_label: str | None
    file_url: str | None
    excerpt: str | None
    method: str
    score: float | None
    confirmed: bool


class RuleOut(ORM):
    id: uuid.UUID
    code: str
    description: str
    logic: Any
    applies_when: Any | None
    impact: str | None
    severity: str
    fields: list[str]
    enabled: bool
    declared_clause_ref: str | None
    clause_link: ClauseLinkOut | None


class RuleSetOut(ORM):
    id: uuid.UUID
    name: str
    regulator: str
    jurisdiction: str | None
    version_number: int
    status: str
    source_filename: str
    rule_count: int
    lint: list[LintIssueOut]
    uploaded_at: datetime
    source_document_id: uuid.UUID | None


class RuleSetDetail(RuleSetOut):
    rules: list[RuleOut]


class RuleSetUploadResult(BaseModel):
    rule_set: RuleSetDetail
    already_uploaded: bool = False


class RuleFileValidation(BaseModel):
    valid: bool
    regulator: str | None
    rule_count: int
    issues: list[LintIssueOut]


class ClauseLinkIn(BaseModel):
    document_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    clause_id: uuid.UUID | None = None
    clause_ref: str
    page: int | None = None
    citation_label: str | None = None
    file_url: str | None = None
    excerpt: str | None = None


class DatasetOut(ORM):
    id: uuid.UUID
    filename: str
    sha256: str
    file_size: int
    row_count: int
    status: str
    validation: dict[str, Any]
    uploaded_at: datetime


class DatasetUploadResult(BaseModel):
    dataset: DatasetOut
    already_uploaded: bool = False


class RunCreate(BaseModel):
    dataset_id: uuid.UUID
    rule_set_ids: list[uuid.UUID] = Field(default_factory=list, description="Empty = all ACTIVE rule sets")
    document_version_id: uuid.UUID | None = Field(
        None, description="Regulatory document version this analysis " "is performed against (lineage)"
    )


class RunOut(ORM):
    id: uuid.UUID
    dataset_id: uuid.UUID
    rule_set_ids: list[str]
    document_version_id: uuid.UUID | None
    status: str
    total_trades: int
    total_rules: int
    chunks_total: int
    chunks_done: int
    summary: dict[str, Any]
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ResultRow(ORM):
    id: int
    row_number: int
    trade_id: str | None
    asset_class: str | None
    rule_code: str
    regulator: str
    severity: str
    status: str
    explanation: str
    field_values: dict[str, Any]
    clause_ref: str | None
    citation_label: str | None
    source_version_id: uuid.UUID | None


class MatrixColumn(BaseModel):
    rule_code: str
    regulator: str
    description: str
    severity: str
    citation_label: str | None


class MatrixRow(BaseModel):
    trade_id: str | None
    row_number: int
    asset_class: str | None
    fail_count: int
    cells: dict[str, ResultStatus]


class MatrixPage(BaseModel):
    columns: list[MatrixColumn]
    rows: list[MatrixRow]
    total: int
    page: int
    size: int


class RuleStats(BaseModel):
    rule_code: str
    regulator: str
    severity: str
    passed: int
    failed: int
    not_applicable: int
    errors: int
    fail_rate: float


class RunStats(BaseModel):
    run_id: uuid.UUID
    status: str
    total_trades: int
    total_checks: int
    passed: int
    failed: int
    not_applicable: int
    errors: int
    pass_rate: float = Field(description="passed / (passed + failed)")
    trades_with_failures: int
    compliant_trades: int
    by_rule: list[RuleStats]
    by_regulator: dict[str, dict[str, int]]
    by_asset_class: dict[str, dict[str, int]]


class EvaluateRequest(BaseModel):
    trade: dict[str, Any] = Field(examples=[{"Trade_ID": "T1", "Asset_Class": "Equity", "Price": -1}])
    rule_set_ids: list[uuid.UUID] = Field(default_factory=list)


class OutcomeOut(BaseModel):
    rule_code: str
    regulator: str
    status: ResultStatus
    explanation: str
    field_values: dict[str, Any]
    citation_label: str | None


class EvaluateResponse(BaseModel):
    trade_id: str | None
    compliant: bool
    outcomes: list[OutcomeOut]
