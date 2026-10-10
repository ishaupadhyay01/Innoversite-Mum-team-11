import { getJson, postForm, request } from "./client";
import type {
  Alert,
  Clause,
  IngestionStats,
  MatchSuggestionResponse,
  Page,
  RegDocument,
  RegDocumentDetail,
  UploadAccepted,
  VersionDiff,
  WhatsNewCard,
} from "./types";

export interface NewDocumentInput {
  file: File;
  regulator: string;
  title?: string;
  jurisdiction?: string;
  category?: string;
  effective_date?: string;
  version_label?: string;
}

export const ingestionApi = {
  listDocuments: (q: { page?: number; size?: number; q?: string; regulator?: string }) =>
    getJson<Page<RegDocument>>("/api/v1/documents", q),
  getDocument: (id: string) => getJson<RegDocumentDetail>(`/api/v1/documents/${id}`),
  stats: () => getJson<IngestionStats>("/api/v1/documents/stats"),
  matchSuggestions: (file: File, regulator?: string, title?: string) =>
    postForm<MatchSuggestionResponse>("/api/v1/documents/match-suggestions", { file, regulator, title }),
  uploadNew: (input: NewDocumentInput) =>
    postForm<UploadAccepted>("/api/v1/documents", { ...input, activate: "true" }),
  uploadVersion: (documentId: string, file: File, version_label?: string, effective_date?: string) =>
    postForm<UploadAccepted>(`/api/v1/documents/${documentId}/versions`, {
      file,
      version_label,
      effective_date,
      activate: "true",
    }),
  clauses: (versionId: string) => getJson<Clause[]>(`/api/v1/versions/${versionId}/clauses`),
  activate: (versionId: string) => request(`/api/v1/versions/${versionId}/activate`, { method: "POST" }),
  diff: (versionId: string, against?: string) =>
    getJson<VersionDiff>(`/api/v1/versions/${versionId}/diff`, { against }),
  whatsNew: (page = 1, size = 10) => getJson<Page<WhatsNewCard>>("/api/v1/whats-new", { page, size }),
  alerts: (unreadOnly = false) => getJson<Alert[]>("/api/v1/alerts", { unread_only: unreadOnly }),
  markAlertRead: (id: string) => request(`/api/v1/alerts/${id}/read`, { method: "POST" }),
  markAllAlertsRead: () => request("/api/v1/alerts/read-all", { method: "POST" }),
};
