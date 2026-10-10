// Thin fetch wrapper for the Reg IRIS gateway (/api). Errors carry the backend's error envelope.
import type {
  AlertPage,
  Alert,
  AnalysisRun,
  AuditEvent,
  ChecklistResponse,
  CompareResult,
  DashboardStats,
  Dataset,
  DocumentDetail,
  DocumentFamily,
  FamilyMatch,
  FilterValues,
  GapResponse,
  ImpactPage,
  ImpactResultDetail,
  ImportRun,
  Page,
  ParagraphWithContext,
  RelatedText,
  Rule,
  RulesResponse,
  SearchRequest,
  SearchResponse,
  Suggestion,
  SystemStatus,
  TradeQueryResponse,
  TradeVerdictPage,
  UploadJob,
  Version,
  VersionDetail,
} from "../types/api";

const TOKEN_KEY = "reg-iris.api-token";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getApiToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setApiToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token stays in memory for this request only */
  }
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export function toQuery(params: Params = {}): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => usp.append(key, String(v)));
    else usp.append(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getApiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error", "The Reg IRIS API is not reachable. Check that the containers are running.");
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    throw new ApiError(
      response.status,
      err?.code ?? "http_error",
      err?.message ?? `Request failed with status ${response.status}`,
      err?.details,
    );
  }
  return data as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  // dashboard & system
  dashboard: () => request<DashboardStats>("/dashboard/stats"),
  system: () => request<SystemStatus>("/system/status"),
  latestImport: () => request<ImportRun | null>("/imports/latest"),
  runImport: () => request<{ status: string }>("/imports/run", { method: "POST" }),
  audit: (limit = 30) => request<AuditEvent[]>(`/audit${toQuery({ limit })}`),

  // documents
  documents: (params: Params) => request<Page<DocumentFamily>>(`/documents${toQuery(params)}`),
  document: (id: number) => request<DocumentDetail>(`/documents/${id}`),
  versions: (id: number) => request<Version[]>(`/documents/${id}/versions`),
  version: (versionId: number) => request<VersionDetail>(`/documents/versions/${versionId}`),
  matchFamily: (fileName: string, regulator?: string) =>
    request<FamilyMatch[]>(`/documents/match${toQuery({ file_name: fileName, regulator })}`),
  upload: (form: FormData) =>
    request<{ job_id: string; status: string; status_url: string }>("/documents/upload", { method: "POST", body: form }),
  uploadJob: (jobId: string) => request<UploadJob>(`/documents/uploads/${jobId}`),
  uploadJobs: () => request<UploadJob[]>("/documents/uploads?limit=10"),
  compare: (base: number, target: number) =>
    request<CompareResult>(`/documents/compare${toQuery({ base_version_id: base, target_version_id: target })}`),

  // search
  search: (body: SearchRequest) => post<SearchResponse>("/search", body),
  suggestions: (q: string) => request<Suggestion[]>(`/search/suggestions${toQuery({ q, limit: 8 })}`),
  filters: () => request<FilterValues>("/search/filters"),
  paragraph: (id: string, context = 1) => request<ParagraphWithContext>(`/search/paragraphs/${encodeURIComponent(id)}${toQuery({ context })}`),

  // alerts
  alerts: (params: Params) => request<AlertPage>(`/alerts${toQuery(params)}`),
  unreadCount: () => request<{ unread: number; latest_id: number | null }>("/alerts/unread-count"),
  markAlert: (id: number, isRead: boolean) =>
    request<Alert>(`/alerts/${id}/read`, { method: "PATCH", body: JSON.stringify({ is_read: isRead }) }),
  readAll: () => request<{ updated: number }>("/alerts/read-all", { method: "POST" }),

  // rules & analysis
  rules: () => request<RulesResponse>("/rules"),
  rule: (id: string) => request<Rule & { related_text: RelatedText }>(`/rules/${encodeURIComponent(id)}`),
  validateRules: (body: unknown) => post<{ valid: boolean } & Record<string, unknown>>("/rules/validate", body),
  reloadRules: () => request<{ rules: number; added: string[]; removed: string[]; invalid: string[] }>("/rules/reload", { method: "POST" }),
  datasets: () => request<Dataset[]>("/trades/datasets"),
  runAnalysis: (body: { dataset?: string | null; regulators: string[]; rule_ids: string[] }) => post<AnalysisRun>("/impact-matrix", body),
  analyses: () => request<AnalysisRun[]>("/impact-matrix?limit=10"),
  latestAnalysis: () => request<AnalysisRun | null>("/impact-matrix/latest"),
  matrix: (id: string, params: Params) => request<ImpactPage>(`/impact-matrix/${id}${toQuery(params)}`),
  matrixRow: (id: string, rowId: number) => request<ImpactResultDetail>(`/impact-matrix/${id}/results/${rowId}`),
  exportUrl: (id: string, params: Params = {}) => `/api/impact-matrix/${id}/export${toQuery(params)}`,
  summaryExportUrl: (id: string) => `/api/impact-matrix/${id}/export/summary`,
  tradeVerdicts: (id: string, params: Params) => request<TradeVerdictPage>(`/impact-matrix/${id}/trades${toQuery(params)}`),
  tradeVerdictExportUrl: (id: string, params: Params = {}) => `/api/impact-matrix/${id}/export/trades${toQuery(params)}`,
  gap: (body: { dataset?: string | null; regulators: string[]; include_schema_validation: boolean }) => post<GapResponse>("/gap-analysis", body),
  checklist: (params: Params) => request<ChecklistResponse>(`/checklist${toQuery(params)}`),
  tradeQuery: (question: string, dataset?: string | null) => post<TradeQueryResponse>("/trades/query", { question, dataset }),
};

/** Download through fetch so the optional bearer token is sent, then save as a file. */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const headers = new Headers();
  const token = getApiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { headers });
  if (!response.ok) {
    let message = `Download failed (${response.status})`;
    try {
      message = (await response.json()).error?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, "download_failed", message);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = match?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
