import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { searchApi } from "@/api/search";
import type { SearchMode, SearchParams } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { FilterPanel } from "./FilterPanel";
import { SearchResultCard } from "./SearchResultCard";

const EXAMPLES = ["counterparty LEI requirement", "FX trades", "reporting deadline", "record retention"];

export function SearchPage() {
  const [url, setUrl] = useSearchParams();
  const [draft, setDraft] = useState(url.get("q") ?? "");
  const [params, setParams] = useState<SearchParams>({
    q: url.get("q") ?? "", mode: "keyword", regulator: [], jurisdiction: [], category: [], status: "ACTIVE", page: 1, size: 10,
  });
  const facets = useQuery({ queryKey: ["facets"], queryFn: searchApi.facets });
  const results = useQuery({
    queryKey: ["search", params],
    queryFn: () => searchApi.search(params),
    enabled: params.q.trim().length > 0,
  });

  const submit = (q: string) => {
    setParams({ ...params, q, page: 1 });
    setUrl(q ? { q } : {});
  };

  return (
    <>
      <PageHeader title="Search regulations" subtitle="Find the exact clause, with a citation you can click" />
      <form className="mb-5 flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(draft); }}>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-faint" />
          <input className="input pl-9" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. Which fields are mandatory for derivatives?" aria-label="Search query" />
        </div>
        <div className="flex rounded-md border border-line bg-white p-0.5" role="radiogroup" aria-label="Search mode">
          {(["keyword", "semantic"] as SearchMode[]).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={params.mode === m}
              onClick={() => setParams({ ...params, mode: m, page: 1 })}
              className={`rounded px-3 text-sm capitalize ${params.mode === m ? "bg-brand text-white" : "text-ink-soft"}`}>
              {m}
            </button>
          ))}
        </div>
      </form>
      <div className="grid gap-6 md:grid-cols-[220px_1fr]">
        <FilterPanel facets={facets.data} value={params} onChange={(f) => setParams({ ...params, ...f, page: 1 })} />
        <div className="space-y-3">
          {!params.q && (
            <EmptyState title="Ask about any regulation">
              Try:{" "}
              {EXAMPLES.map((ex) => (
                <button key={ex} className="mx-1 text-brand hover:underline" onClick={() => { setDraft(ex); submit(ex); }}>{ex}</button>
              ))}
            </EmptyState>
          )}
          <ErrorBanner error={results.error} />
          {results.isFetching && <Spinner label="Searching…" />}
          {results.data && (
            <>
              <div className="text-xs text-ink-soft">{results.data.total} clauses · {results.data.took_ms} ms</div>
              {results.data.hits.map((h) => <SearchResultCard key={h.clause_id} hit={h} />)}
              {results.data.total === 0 && <EmptyState title="No matching clauses">Try fewer words or clear filters.</EmptyState>}
              {results.data.total > params.size && (
                <Pagination page={params.page} pages={Math.ceil(results.data.total / params.size)} total={results.data.total}
                  onPage={(page) => setParams({ ...params, page })} />
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
