// Mirrors the Pydantic schemas of the three services. Keep in sync with docs/API.md.

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown>; request_id: string | null };
}

// ── Module 1: ingestion & versioning ─────────────────────────────────────
export type VersionStatus = "ACTIVE" | "INACTIVE";
export type ProcessingStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  version_label: string;
  status: VersionStatus;
  processing_status: ProcessingStatus;
  original_filename: string;
  mime_type: string;
  file_size: number;
  sha256: string;
  effective_date: string | null;
  page_count: number | null;
  clause_count: number | null;
  quality_warnings: string[] | null;
  error_message: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
  processed_at: string | null;
  activated_at: string | null;
  file_url: string | null;
}

export interface RegDocument {
  id: string;
  document_key: string;
  title: string;
  regulator: string;
  jurisdiction: string | null;
  category: string | null;
  active_version_id: string | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  active_version: DocumentVersion | null;
}

export interface RegDocumentDetail extends RegDocument {
  versions: DocumentVersion[];
}

export interface UploadAccepted {
  document: RegDocument;
  version: DocumentVersion;
  message: string;
}

export interface MatchCandidate {
  document_id: string;
  document_key: string;
  title: string;
  regulator: string;
  active_version_id: string | null;
  active_version_label: string | null;
  score: number;
  reasons: string[];
}

export interface MatchSuggestionResponse {
  sha256: string;
  recommendation: "DUPLICATE" | "NEW_VERSION" | "NEW_DOCUMENT";
  exact_duplicate: { document_id: string; version_id: string; title: string; version_label: string } | null;
  candidates: MatchCandidate[];
}

export interface Clause {
  id: string;
  ordinal: number;
  clause_ref: string;
  title: string | null;
  text: string;
  page_start: number;
  page_end: number;
  anchor: string | null;
}

export type ChangeType = "ADDED" | "REMOVED" | "MODIFIED" | "UNCHANGED";

export interface InlineOp {
  op: "equal" | "insert" | "delete";
  text: string;
}

export interface ClauseChange {
  change: ChangeType;
  clause_ref: string;
  title: string | null;
  old_text: string | null;
  new_text: string | null;
  old_page: number | null;
  new_page: number | null;
  similarity: number;
  inline: InlineOp[];
}

export interface VersionDiff {
  document_id: string;
  from_version_id: string;
  to_version_id: string;
  summary: Record<ChangeType, number>;
  headline: string;
  changes: ClauseChange[];
}

export interface WhatsNewCard {
  id: string;
  card_type: "NEW_DOCUMENT" | "NEW_VERSION";
  document_id: string;
  version_id: string;
  diff_id: string | null;
  regulator: string;
  title: string;
  effective_date: string | null;
  headline: string;
  summary: Partial<Record<ChangeType, number>>;
  highlights: { clause_ref: string; title: string | null; change: ChangeType; page: number | null; excerpt?: string }[];
  created_at: string;
}

export interface Alert {
  id: string;
  card_id: string | null;
  level: string;
  message: string;
  created_at: string;
  read_at: string | null;
}

export interface IngestionStats {
  documents: number;
  versions: number;
  active_versions: number;
  processing: number;
  failed: number;
  by_regulator: Record<string, number>;
}

// ── Module 2: search & comparison ────────────────────────────────────────
export type SearchMode = "keyword" | "semantic";

export interface Citation {
  document_id: string;
  version_id: string;
  document_title: string;
  file_name: string;
  regulator: string;
  version_label: string;
  clause_ref: string;
  clause_title: string | null;
  page: number;
  anchor: string | null;
  file_url: string;
  label: string;
}

export interface SearchHit {
  clause_id: string;
  score: number;
  text: string;
  highlights: string[];
  status: VersionStatus;
  effective_date: string | null;
  jurisdiction: string | null;
  category: string | null;
  citation: Citation;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  total: number;
  page: number;
  size: number;
  took_ms: number;
  hits: SearchHit[];
}

export interface SearchParams {
  q: string;
  mode: SearchMode;
  regulator: string[];
  jurisdiction: string[];
  category: string[];
  status: "ACTIVE" | "INACTIVE" | "ALL";
  effective_from?: string;
  effective_to?: string;
  page: number;
  size: number;
}

export interface FacetBucket {
  value: string;
  count: number;
}

export interface Facets {
  regulator: FacetBucket[];
  jurisdiction: FacetBucket[];
  category: FacetBucket[];
  status: FacetBucket[];
}

export interface Comparison {
  id: string;
  left_version_id: string;
  right_version_id: string;
  left_label: string;
  right_label: string;
  summary: Record<ChangeType, number>;
  changes: ClauseChange[];
  created_at: string;
}

// ── Module 3: rules & impact analysis ────────────────────────────────────
export type ResultStatus = "PASS" | "FAIL" | "NOT_APPLICABLE" | "ERROR";

export interface LintIssue {
  level: "ERROR" | "WARNING" | "INFO";
  rule_code: string | null;
  message: string;
}

export interface RuleSet {
  id: string;
  name: string;
  regulator: string;
  jurisdiction: string | null;
  version_number: number;
  status: VersionStatus;
  source_filename: string;
  rule_count: number;
  lint: LintIssue[];
  uploaded_at: string;
  source_document_id: string | null;
}

export interface RuleFileValidation {
  valid: boolean;
  regulator: string | null;
  rule_count: number;
  issues: LintIssue[];
}

export interface TradeDataset {
  id: string;
  filename: string;
  sha256: string;
  file_size: number;
  row_count: number;
  status: "VALID" | "VALID_WITH_WARNINGS" | "INVALID";
  validation: {
    errors: string[];
    missing_columns: string[];
    extra_columns: string[];
    duplicate_trade_ids: number;
    issue_counts: Record<string, Record<string, number>>;
    sample_issues: { row: number; trade_id: string | null; field: string; issue: string; value: string }[];
  };
  uploaded_at: string;
}

export interface Run {
  id: string;
  dataset_id: string;
  rule_set_ids: string[];
  document_version_id: string | null;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  total_trades: number;
  total_rules: number;
  chunks_total: number;
  chunks_done: number;
  summary: Record<string, number>;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ResultRow {
  id: number;
  row_number: number;
  trade_id: string | null;
  asset_class: string | null;
  rule_code: string;
  regulator: string;
  severity: string;
  status: ResultStatus;
  explanation: string;
  field_values: Record<string, unknown>;
  clause_ref: string | null;
  citation_label: string | null;
  source_version_id: string | null;
}

export interface RuleStats {
  rule_code: string;
  regulator: string;
  severity: string;
  passed: number;
  failed: number;
  not_applicable: number;
  errors: number;
  fail_rate: number;
}

export interface RunStats {
  run_id: string;
  status: string;
  total_trades: number;
  total_checks: number;
  passed: number;
  failed: number;
  not_applicable: number;
  errors: number;
  pass_rate: number;
  trades_with_failures: number;
  compliant_trades: number;
  by_rule: RuleStats[];
  by_regulator: Record<string, Record<string, number>>;
  by_asset_class: Record<string, Record<string, number>>;
}

export interface ResultFilters {
  status: ResultStatus[];
  rule_code: string[];
  regulator: string[];
  asset_class: string[];
  trade_id?: string;
  q?: string;
}
