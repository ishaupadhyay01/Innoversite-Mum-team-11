import { getJson, postJson } from "./client";
import type { Comparison, Facets, SearchParams, SearchResponse } from "./types";

export const searchApi = {
  search: (p: SearchParams) => getJson<SearchResponse>("/api/v1/search", { ...p }),
  facets: () => getJson<Facets>("/api/v1/search/facets"),
  compare: (left_version_id: string, right_version_id: string, include_unchanged = false) =>
    postJson<Comparison>("/api/v1/compare", { left_version_id, right_version_id, include_unchanged }),
};
