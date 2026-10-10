import { getJson, postForm, postJson, toQueryString } from "./client";
import type {
  Page,
  ResultFilters,
  ResultRow,
  RuleFileValidation,
  RuleSet,
  Run,
  RunStats,
  TradeDataset,
} from "./types";

export const rulesApi = {
  listRuleSets: () => getJson<RuleSet[]>("/api/v1/rule-sets"),
  validateRules: (file: File) => postForm<RuleFileValidation>("/api/v1/rule-sets/validate", { file }),
  uploadRules: (file: File, source_document_id?: string) =>
    postForm<{ rule_set: RuleSet; already_uploaded: boolean }>("/api/v1/rule-sets", { file, source_document_id }),
  uploadDataset: (file: File) =>
    postForm<{ dataset: TradeDataset; already_uploaded: boolean }>("/api/v1/datasets", { file }),
  listDatasets: () => getJson<TradeDataset[]>("/api/v1/datasets"),
  startRun: (dataset_id: string, rule_set_ids: string[], document_version_id?: string) =>
    postJson<Run>("/api/v1/runs", { dataset_id, rule_set_ids, document_version_id }),
  listRuns: () => getJson<Run[]>("/api/v1/runs"),
  getRun: (id: string) => getJson<Run>(`/api/v1/runs/${id}`),
  stats: (id: string) => getJson<RunStats>(`/api/v1/runs/${id}/stats`),
  results: (id: string, f: ResultFilters, page: number, size: number, sort = "row_number", desc = false) =>
    getJson<Page<ResultRow>>(`/api/v1/runs/${id}/results`, { ...f, page, size, sort, desc }),
  exportUrl: (id: string, f: ResultFilters) => `/api/v1/runs/${id}/export.csv${toQueryString({ ...f })}`,
};
