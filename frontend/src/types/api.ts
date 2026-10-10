// Types mirroring the backend response models (see services/*/app/schemas.py).

export type SourceType = "pdf" | "html" | "txt";
export type EvalStatus = "PASS" | "FAIL" | "NOT_APPLICABLE" | "ERROR";

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown; request_id?: string | null };
}

export interface Version {
  id: number;
  document_id: number;
  version_label: string;
  version_seq: number;
  parent_version_id: number | null;
  file_name: string;
  source_type: SourceType;
  content_hash: string;
  file_size: number;
  effective_date: string | null;
  uploaded_at: string;
  origin: "seed" | "upload";
  is_latest: boolean;
  status: string;
  status_detail: string | null;
  title: string | null;
  page_count: number | null;
  paragraph_count: number;
  extractor: string | null;
  warnings: string[];
  metadata_notes: string[];
  indexed_at: string | null;
  source_url: string;
}

export interface DocumentFamily {
  id: number;
  family_key: string;
  title: string;
  regulator: string;
  jurisdiction: string | null;
  category: string | null;
  version_count: number;
  latest_version: Version | null;
  created_at: string;
}

export interface DocumentDetail extends DocumentFamily {
  versions: Version[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Paragraph {
  paragraph_id: string;
  ordinal: number;
  heading: string | null;
  body: string;
  page_start: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  anchor: string | null;
  location: string;
}

export interface VersionDetail {
  version: Version;
  document: DocumentFamily;
  paragraphs: Paragraph[];
}

export interface UploadJob {
  id: string;
  file_name: string;
  status: "queued" | "processing" | "indexed" | "failed";
  detail: string | null;
  document_id: number | null;
  version_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface FamilyMatch {
  document_id: number;
  title: string;
  regulator: string;
  latest_version_label: string | null;
  suggested_version_label: string;
  reason: string;
}

export interface Alert {
  id: number;
  document_id: number;
  version_id: number;
  previous_version_id: number | null;
  change_type: string;
  change_types: string[];
  title: string;
  summary: string;
  regulator: string;
  document_name: string;
  previous_version_label: string | null;
  new_version_label: string;
  effective_date: string | null;
  diff_stats: Record<string, number>;
  source: "initial_import" | "upload";
  is_read: boolean;
  event_time: string;
  created_at: string;
}

export interface AlertPage extends Page<Alert> {
  unread: number;
}

export interface DiffClause {
  ordinal: number;
  heading: string | null;
  body: string;
  page_start: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  anchor: string | null;
  location: string;
}

export interface DiffRow {
  change: "unchanged" | "added" | "removed" | "modified";
  old: DiffClause | null;
  new: DiffClause | null;
  similarity: number | null;
  inline: { op: "equal" | "insert" | "delete"; text: string }[] | null;
}

export interface CompareResult {
  base: Version;
  target: Version;
  same_document: boolean;
  stats: Record<string, number>;
  summary: string;
  change_types: string[];
  rows: DiffRow[];
  method: string;
}

export interface Segment {
  text: string;
  highlight: boolean;
}

export interface Citation {
  regulator: string;
  document_name: string;
  document_title: string | null;
  version: string;
  source_type: SourceType;
  page_start: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  section_heading: string | null;
  anchor: string | null;
  location_label: string;
  source_url: string;
  viewer_url: string;
}

export interface SearchHit {
  paragraph_id: string;
  score: number | null;
  document_id: string;
  document_version_id: string;
  regulator: string;
  jurisdiction: string | null;
  category: string | null;
  effective_date: string | null;
  is_latest: boolean;
  heading: string | null;
  heading_segments: Segment[];
  text_segments: Segment[];
  citation: Citation;
  identical_text_in: { paragraph_id: string; document_name: string; version: string; location_label: string }[];
}

export interface FacetBucket {
  value: string;
  count: number;
}

export interface SearchFilters {
  regulators: string[];
  jurisdictions: string[];
  categories: string[];
  source_types: SourceType[];
  versions: string[];
  document_ids: string[];
  effective_from: string | null;
  effective_to: string | null;
  uploaded_from?: string | null;
  uploaded_to?: string | null;
}

export type SearchScope = "latest" | "all" | "version";
export type SearchSort = "relevance" | "newest" | "effective_date" | "document_name";

export interface SearchRequest {
  query: string;
  filters: SearchFilters;
  scope: SearchScope;
  version_id?: string | null;
  sort: SearchSort;
  match_mode?: "smart" | "all" | "any";
  page: number;
  page_size: number;
}

export interface SearchResponse {
  query: string;
  interpreted: { terms: string[]; phrases: string[]; excluded: string[]; match_mode: string };
  total: number;
  took_ms: number;
  es_took_ms: number | null;
  page: number;
  page_size: number;
  total_pages: number;
  scope: SearchScope;
  version_id: string | null;
  sort: SearchSort;
  relaxed: boolean;
  results: SearchHit[];
  facets: Record<string, FacetBucket[]>;
  did_you_mean: string | null;
  notices: string[];
}

export interface FilterValues {
  regulator: FacetBucket[];
  jurisdiction: FacetBucket[];
  category: FacetBucket[];
  source_type: FacetBucket[];
  version: FacetBucket[];
  document_versions: { version_id: string; document_id: string; label: string; regulator: string; is_latest: boolean; paragraphs: number }[];
  effective_date_range: { min: string | null; max: string | null };
}

export interface Suggestion {
  text: string;
  type: "heading" | "regulator" | "history" | "category";
  detail: string | null;
}

export interface ParagraphWithContext {
  paragraph: ParagraphDoc;
  context: ParagraphDoc[];
}

export interface ParagraphDoc {
  paragraph_id: string;
  ordinal: number;
  heading: string | null;
  text: string;
  citation: Citation;
  is_latest: boolean;
}

export interface Rule {
  id: string;
  regulator: string;
  jurisdiction: string | null;
  description: string;
  impact: string | null;
  severity: string | null;
  source_file: string;
  rule_source: string;
  source_logic: unknown;
  logic: unknown;
  logic_text: string;
  applies_when: unknown;
  applies_when_text: string | null;
  applies_when_source: "rule" | "overlay" | null;
  applies_when_rationale: string | null;
  citation: Record<string, unknown> | null;
  fields: string[];
  normalization_notes: string[];
  errors: string[];
  warnings: string[];
  valid: boolean;
}

export interface RuleSet {
  file_name: string;
  regulator: string;
  jurisdiction: string | null;
  rule_count: number;
  content_hash: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
  rules: Rule[];
}

export interface RulesResponse {
  loaded_at: string | null;
  rules_dir: string;
  rule_sets: RuleSet[];
  total_rules: number;
  valid_rules: number;
  regulators: string[];
  schema: { source: string | null; fields: string[]; required: string[]; normalization_notes: string[] };
  overlay: { source: string | null; field_aliases: Record<string, string>; rules: string[] };
  load_errors: string[];
}

export interface RelatedText {
  status: string;
  method?: string;
  query?: string;
  detail?: string;
  items: {
    paragraph_id: string;
    heading: string | null;
    document_name: string;
    version: string;
    location_label: string;
    source_url: string;
    viewer_url: string;
    excerpt: string;
  }[];
}

export interface CountRow {
  pass: number;
  fail: number;
  not_applicable: number;
  error: number;
}

export interface AnalysisSummary {
  total_trades: number;
  total_rules: number;
  total_evaluations: number;
  status_counts: Record<EvalStatus, number>;
  unique_impacted_trades: number;
  trades_with_errors: number;
  fully_compliant_trades: number;
  trade_compliance_rate: number | null;
  by_regulator: (CountRow & { regulator: string; impacted_trades: number })[];
  by_rule: (CountRow & { rule_id: string; regulator: string | null; description: string | null; severity: string | null })[];
  by_asset_class: { asset_class: string; trades: number; impacted_trades: number; fail: number }[];
  by_category: { category: string; label: string; count: number }[];
  top_impacted_trades: { trade_id: string; fail_count: number; rule_ids: string[] }[];
  dataset_warnings?: string[];
  /** The selected rules combined with AND (absent on runs made before this feature). */
  combined?: CombinedSummary;
}

export interface CombinedSummary {
  logic: "AND";
  rule_ids: string[];
  expression: string;
  description: string;
  trades: number;
  status_counts: Record<EvalStatus, number>;
  compliant_trades: number;
  non_compliant_trades: number;
  undetermined_trades: number;
  compliance_rate: number | null;
}

export interface TradeVerdict {
  trade_id: string;
  asset_class: string | null;
  overall: EvalStatus;
  compliant: boolean;
  rules_evaluated: number;
  failed_rule_ids: string[];
  error_rule_ids: string[];
  passed_rule_ids: string[];
  not_applicable_rule_ids: string[];
  failures: { rule_id: string; regulator: string | null; status: EvalStatus; affected_fields: string[]; explanation: string | null }[];
  reason: string;
}

export interface TradeVerdictPage {
  analysis_id: string;
  combined: CombinedSummary;
  items: TradeVerdict[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnalysisRun {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  dataset: string;
  dataset_hash: string | null;
  regulators: string[];
  rule_ids: string[];
  summary: AnalysisSummary;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  rules?: { id: string; regulator: string; description: string; rule_source: string; applies_when_text: string | null; logic_text: string; severity: string | null }[];
}

export interface ImpactRow {
  id: number;
  trade_id: string;
  asset_class: string | null;
  regulator: string;
  rule_id: string;
  rule_description: string;
  status: EvalStatus;
  affected_fields: string[];
  actual_values: Record<string, unknown>;
  expected_condition: string;
  explanation: string;
  rule_source: string;
  severity: string | null;
  category: string | null;
  conditional: boolean;
}

export interface ImpactPage {
  analysis: AnalysisRun;
  items: ImpactRow[];
  total: number;
  distinct_trades: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ImpactResultDetail {
  result: ImpactRow;
  trade: Record<string, unknown> | null;
  rule: Rule | null;
  related_text: RelatedText;
  analysis: { id: string; dataset: string; dataset_hash: string | null; finished_at: string | null };
}

export interface Dataset {
  name: string;
  trades: number;
  columns: string[];
  warnings: string[];
  default: boolean;
}

export interface ChecklistItem {
  rule_id: string;
  regulator: string;
  description: string;
  applicability: string;
  status: string;
  explanation: string;
  rule_source: string;
  pass?: number;
  fail?: number;
  not_applicable?: number;
  error?: number;
  applicable?: number;
  compliance_rate?: number | null;
  affected_fields?: string[];
  actual_values?: Record<string, unknown>;
}

export interface ChecklistResponse {
  scope: "dataset" | "trade";
  dataset: string;
  trades: number;
  regulators: string[];
  items: ChecklistItem[];
  trade?: Record<string, unknown>;
  by_regulator?: Record<string, string | number>[];
}

export interface GapCategory {
  category: string;
  label: string;
  failed_evaluations: number;
  impacted_trades: number;
  trade_ids: string[];
  rule_ids: string[];
  fields: string[];
  examples: { trade_id: string; rule_id: string; explanation: string }[];
}

export interface GapResponse {
  dataset: string;
  trades: number;
  regulators: string[];
  rules_evaluated: string[];
  rule_findings: {
    total_failed_evaluations: number;
    impacted_trades: number;
    by_category: GapCategory[];
    conditional_requirements: { failed_evaluations: number; impacted_trades: number; rule_ids: string[] };
  };
  schema_findings: {
    enabled: boolean;
    total: number;
    impacted_trades?: number;
    by_check: { field: string; check: string; count: number; trade_ids: string[]; example: string }[];
  };
  notes: string[];
}

export interface TradeQueryResponse {
  matched: boolean;
  message?: string;
  supported_patterns?: string[];
  dataset?: string;
  interpretation?: string;
  count?: number;
  count_only?: boolean;
  trades?: Record<string, unknown>[];
}

export interface AuditEvent {
  id: number;
  service: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string;
  created_at: string;
}

export interface ImportRun {
  id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  files_total: number;
  files_processed: number;
  files_skipped: number;
  files_failed: number;
  log: string[];
  errors: string[];
}

export interface DocumentStats {
  documents: number;
  versions: number;
  regulators: number;
  paragraphs_recorded: number;
  status_counts: Record<string, number>;
  versions_by_regulator: { regulator: string; versions: number }[];
  unread_alerts: number;
  latest_versions: Version[];
}

export interface IndexStats {
  paragraphs_total: number;
  paragraphs_latest: number;
  versions_indexed: number;
  documents_indexed: number;
  paragraphs_by_regulator: { regulator: string; paragraphs: number }[];
  index: string;
}

export interface SearchAnalytics {
  total_searches: number;
  window_days: number;
  searches_in_window: number;
  avg_response_ms: number | null;
  zero_result_rate: number | null;
  top_queries: { query: string; count: number; avg_hits: number }[];
  zero_result_queries: { query: string; count: number }[];
  per_day: { day: string; searches: number; avg_ms: number }[];
  recent: { query: string; total_hits: number; took_ms: number; scope: string; created_at: string }[];
}

export interface DashboardStats {
  generated_at: string;
  documents: DocumentStats | null;
  index: IndexStats | null;
  search: SearchAnalytics | null;
  alerts: AlertPage | null;
  activity: AuditEvent[] | null;
  analysis: AnalysisRun | null;
  rules: { total_rules: number; valid_rules: number; regulators: string[]; rule_sets: number } | null;
  errors: string[];
}

export interface HealthCheck {
  ok: boolean;
  detail: string;
}

export interface SystemStatus {
  generated_at: string;
  overall: string;
  gateway: { status: string; api_token_required: boolean };
  services: { name: string; url: string; reachable: boolean; status: string; latency_ms: number; checks: Record<string, HealthCheck>; error: string | null }[];
  elasticsearch: HealthCheck;
  postgresql: HealthCheck;
  rules: HealthCheck | null;
  import: ImportRun | null;
  index: IndexStats | null;
  links: { swagger_ui: string; openapi: string };
}
