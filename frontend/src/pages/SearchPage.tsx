import { keepPreviousData, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Clock3, Copy, ExternalLink, FileText, History, Search as SearchIcon, SlidersHorizontal, Table2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Button,
  CheckList,
  EmptyState,
  ErrorState,
  Notice,
  Pagination,
  Segmented,
  Select,
  SegmentText,
  SkeletonRows,
  Tag,
  inputClass,
} from "../components/ui";
import { useDebounce } from "../hooks/useDebounce";
import { api } from "../services/api";
import type { FacetBucket, SearchFilters, SearchHit, SearchRequest, SearchScope, SearchSort } from "../types/api";
import { formatDate } from "../utils/format";

const EXAMPLES = ["Counterparty LEI", '"Mandatory Trade Reporting Fields"', "EMIR derivatives", "FCA FX trades", "Negative price", "Reporting deadline"];

const EMPTY_FILTERS: SearchFilters = {
  regulators: [],
  jurisdictions: [],
  categories: [],
  source_types: [],
  versions: [],
  document_ids: [],
  effective_from: null,
  effective_to: null,
};

function hasFilters(f: SearchFilters): boolean {
  return Boolean(f.regulators.length || f.jurisdictions.length || f.categories.length || f.source_types.length || f.effective_from || f.effective_to);
}

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  const [input, setInput] = useState(urlQuery);
  const [filters, setFilters] = useState<SearchFilters>(() => ({
    ...EMPTY_FILTERS,
    regulators: params.getAll("regulator"),
  }));
  const [scope, setScope] = useState<SearchScope>((params.get("scope") as SearchScope) || "latest");
  const [versionId, setVersionId] = useState<string>(params.get("version") ?? "");
  const [sort, setSort] = useState<SearchSort>("relevance");
  const [page, setPage] = useState(1);
  const [showSuggest, setShowSuggest] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setInput(urlQuery), [urlQuery]);
  useEffect(() => setPage(1), [urlQuery, filters, scope, versionId, sort]);

  const filterValues = useQuery({ queryKey: ["search-filters"], queryFn: api.filters, staleTime: 60_000 });

  const request: SearchRequest = {
    query: urlQuery,
    filters,
    scope: scope === "version" && !versionId ? "latest" : scope,
    version_id: scope === "version" && versionId ? versionId : null,
    sort,
    page,
    page_size: 10,
  };
  const active = urlQuery.trim().length > 0 || hasFilters(filters) || (scope === "version" && !!versionId);
  const search = useQuery({
    queryKey: ["search", request],
    queryFn: () => api.search(request),
    enabled: active,
    placeholderData: keepPreviousData,
  });

  const looksLikeTradeQuestion = /\btrades?\b/i.test(urlQuery) && urlQuery.trim().split(/\s+/).length >= 4;
  const tradeAnswer = useQuery({
    queryKey: ["trade-query", urlQuery],
    queryFn: () => api.tradeQuery(urlQuery),
    enabled: looksLikeTradeQuestion,
  });

  const debounced = useDebounce(input, 200);
  const suggestions = useQuery({
    queryKey: ["suggest", debounced],
    queryFn: () => api.suggestions(debounced),
    enabled: showSuggest && debounced.trim().length >= 2 && debounced !== urlQuery,
    staleTime: 30_000,
  });

  const facets = useMemo(() => {
    const live = search.data?.facets;
    const base = filterValues.data;
    const pick = (name: string): FacetBucket[] => live?.[name] ?? (base ? (base[name as keyof typeof base] as FacetBucket[]) : []) ?? [];
    return {
      regulator: pick("regulator"),
      jurisdiction: pick("jurisdiction"),
      category: pick("category"),
      source_type: pick("source_type"),
    };
  }, [search.data?.facets, filterValues.data]);

  const submit = (value: string) => {
    setShowSuggest(false);
    const next = new URLSearchParams(params);
    if (value.trim()) next.set("q", value.trim());
    else next.delete("q");
    setParams(next);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  const filterPanel = (
    <div className="space-y-6">
      <FilterGroup title="Regulator">
        <CheckList
          options={facets.regulator.map((b) => ({ value: b.value, count: b.count }))}
          selected={filters.regulators}
          onToggle={(v) => setFilters((f) => ({ ...f, regulators: toggle(f.regulators, v) }))}
        />
      </FilterGroup>
      <FilterGroup title="Jurisdiction">
        <CheckList
          options={facets.jurisdiction.map((b) => ({ value: b.value, count: b.count }))}
          selected={filters.jurisdictions}
          onToggle={(v) => setFilters((f) => ({ ...f, jurisdictions: toggle(f.jurisdictions, v) }))}
        />
      </FilterGroup>
      <FilterGroup title="Category">
        <CheckList
          options={facets.category.map((b) => ({ value: b.value, count: b.count }))}
          selected={filters.categories}
          onToggle={(v) => setFilters((f) => ({ ...f, categories: toggle(f.categories, v) }))}
        />
      </FilterGroup>
      <FilterGroup title="Document type">
        <CheckList
          options={facets.source_type.map((b) => ({ value: b.value, label: b.value.toUpperCase(), count: b.count }))}
          selected={filters.source_types}
          onToggle={(v) => setFilters((f) => ({ ...f, source_types: toggle(f.source_types, v as "pdf" | "html" | "txt") }))}
        />
      </FilterGroup>
      <FilterGroup title="Effective date">
        <div className="grid grid-cols-2 gap-2">
          <input
            type="date"
            aria-label="Effective from"
            className={inputClass}
            value={filters.effective_from ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, effective_from: e.target.value || null }))}
          />
          <input
            type="date"
            aria-label="Effective to"
            className={inputClass}
            value={filters.effective_to ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, effective_to: e.target.value || null }))}
          />
        </div>
        {filterValues.data?.effective_date_range.min && (
          <p className="mt-1.5 text-xs text-faint">
            Indexed range {formatDate(filterValues.data.effective_date_range.min)} to {formatDate(filterValues.data.effective_date_range.max)}
          </p>
        )}
      </FilterGroup>
      {hasFilters(filters) && (
        <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setFilters(EMPTY_FILTERS)}>
          Clear filters
        </Button>
      )}
    </div>
  );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Regulatory search</h1>
        <p className="mt-1.5 max-w-[70ch] text-muted">
          Keyword search over every indexed paragraph, ranked by Elasticsearch BM25. Put exact phrases in quotes and exclude words with a minus sign.
        </p>
      </div>

      <form onSubmit={onSubmit} role="search" className="relative">
        <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-faint" aria-hidden />
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            setShowSuggest(true);
          }}
          onFocus={() => setShowSuggest(true)}
          onBlur={() => window.setTimeout(() => setShowSuggest(false), 150)}
          onKeyDown={(e) => e.key === "Escape" && setShowSuggest(false)}
          placeholder='Try Counterparty LEI, "reporting deadline" or EMIR derivatives'
          aria-label="Search query"
          autoFocus
          className="h-14 w-full rounded-lg border border-line bg-surface pl-12 pr-32 text-[17px] shadow-panel placeholder:text-faint focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/15"
        />
        <Button type="submit" variant="primary" className="absolute right-2 top-1/2 -translate-y-1/2" size="md">
          Search
        </Button>
        {showSuggest && (suggestions.data?.length ?? 0) > 0 && (
          <ul className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-pop" role="listbox">
            {suggestions.data!.map((s) => (
              <li key={`${s.type}-${s.text}`}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    if (s.type === "regulator") {
                      setFilters((f) => ({ ...f, regulators: f.regulators.includes(s.text) ? f.regulators : [...f.regulators, s.text] }));
                      setShowSuggest(false);
                    } else {
                      const text = s.type === "heading" ? s.text.replace(/^(paragraph|section|article)\s+\d+\.\s*/i, "") : s.text;
                      setInput(text);
                      submit(text);
                    }
                  }}
                  className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-sunken"
                >
                  {s.type === "history" ? <History className="h-4 w-4 text-faint" /> : s.type === "heading" ? <FileText className="h-4 w-4 text-faint" /> : <SlidersHorizontal className="h-4 w-4 text-faint" />}
                  <span className="flex-1 truncate text-ink">{s.text}</span>
                  <span className="text-xs text-faint">{s.type === "regulator" ? "filter by regulator" : s.detail}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </form>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Segmented
          label="Version scope"
          value={scope}
          onChange={setScope}
          options={[
            { value: "latest", label: "Latest versions" },
            { value: "all", label: "All versions" },
            { value: "version", label: "One version" },
          ]}
        />
        {scope === "version" && (
          <Select
            label="Document version"
            className="w-auto min-w-[260px]"
            value={versionId}
            onChange={setVersionId}
            options={[
              { value: "", label: "Choose a document version…" },
              ...(filterValues.data?.document_versions ?? []).map((v) => ({
                value: v.version_id,
                label: `${v.label}${v.is_latest ? "" : " (historical)"}`,
              })),
            ]}
          />
        )}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="secondary" className="lg:hidden" icon={<SlidersHorizontal className="h-4 w-4" />} onClick={() => setFiltersOpen((v) => !v)}>
            Filters
          </Button>
          <Select
            label="Sort results"
            className="w-auto"
            value={sort}
            onChange={(v) => setSort(v as SearchSort)}
            options={[
              { value: "relevance", label: "Most relevant" },
              { value: "newest", label: "Newest uploaded" },
              { value: "effective_date", label: "Effective date" },
              { value: "document_name", label: "Document name" },
            ]}
          />
        </div>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[230px_1fr]">
        <aside className={clsx("lg:block", filtersOpen ? "block" : "hidden")} aria-label="Search filters">
          {filterPanel}
        </aside>

        <div className="min-w-0">
          {tradeAnswer.data?.matched && (
            <div className="mb-5 rounded-lg border border-accent/30 bg-accent-soft px-5 py-4">
              <div className="flex items-start gap-3">
                <Table2 className="mt-0.5 h-5 w-5 text-accent" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">This reads as a question about the trade data, not the regulations.</p>
                  <p className="mt-1 text-sm text-muted">
                    Answered with structured filters on {tradeAnswer.data.dataset}: <span className="font-mono text-ink">{tradeAnswer.data.interpretation}</span> matches{" "}
                    <strong className="text-ink">{tradeAnswer.data.count}</strong> trade{tradeAnswer.data.count === 1 ? "" : "s"}.
                  </p>
                  {!tradeAnswer.data.count_only && (tradeAnswer.data.trades?.length ?? 0) > 0 && (
                    <p className="mt-2 text-sm text-ink">
                      {(tradeAnswer.data.trades ?? []).slice(0, 12).map((t) => String(t.Trade_ID)).join(", ")}
                      {(tradeAnswer.data.count ?? 0) > 12 && ` and ${(tradeAnswer.data.count ?? 0) - 12} more`}
                    </p>
                  )}
                  <Link to="/impact" className="mt-2 inline-block text-sm font-medium text-accent underline-offset-2 hover:underline">
                    Open impact analysis
                  </Link>
                </div>
              </div>
            </div>
          )}

          {!active && <IntroState onPick={(q) => { setInput(q); submit(q); }} />}
          {active && search.isLoading && <SkeletonRows rows={5} />}
          {active && search.isError && <ErrorState error={search.error} onRetry={() => search.refetch()} />}
          {active && search.data && (
            <>
              <div className="mb-4 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-muted">
                <span>
                  <strong className="text-ink">{search.data.total.toLocaleString("en-GB")}</strong> matching paragraph{search.data.total === 1 ? "" : "s"}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Clock3 className="h-3.5 w-3.5" aria-hidden /> {search.data.took_ms} ms
                </span>
                <span>
                  Searching {search.data.scope === "latest" ? "latest versions" : search.data.scope === "all" ? "all versions, including historical" : "one selected version"}
                </span>
                {search.isFetching && <span className="text-faint">Updating…</span>}
              </div>
              {search.data.notices.length > 0 && (
                <div className="mb-4 space-y-2">
                  {search.data.notices.map((n) => (
                    <Notice key={n} tone={search.data!.relaxed ? "warn" : "info"}>
                      {n}
                    </Notice>
                  ))}
                </div>
              )}
              {search.data.total === 0 ? (
                <EmptyState icon={<SearchIcon className="h-8 w-8" />} title="No paragraph matches this search">
                  {search.data.did_you_mean ? (
                    <>
                      Did you mean{" "}
                      <button className="font-medium text-accent underline underline-offset-2" onClick={() => { setInput(search.data!.did_you_mean!); submit(search.data!.did_you_mean!); }}>
                        {search.data.did_you_mean}
                      </button>
                      ?
                    </>
                  ) : (
                    "Try fewer or different keywords. Results only ever come from the indexed documents."
                  )}
                </EmptyState>
              ) : (
                <ol className="space-y-4">
                  {search.data.results.map((hit, i) => (
                    <ResultItem key={hit.paragraph_id} hit={hit} rank={(search.data!.page - 1) * search.data!.page_size + i + 1} />
                  ))}
                </ol>
              )}
              <div className="mt-6">
                <Pagination page={search.data.page} totalPages={search.data.total_pages} onChange={setPage} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold text-ink">{title}</legend>
      {children}
    </fieldset>
  );
}

function IntroState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="rounded-lg bg-surface p-6 shadow-panel">
      <h2 className="font-semibold">Start with a keyword or a phrase</h2>
      <p className="mt-1 text-sm text-muted">Every result shows the exact paragraph and where it comes from: file, version and page or section.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {EXAMPLES.map((q) => (
          <button key={q} onClick={() => onPick(q)} className="rounded-md border border-line bg-canvas px-3 py-1.5 text-sm text-ink hover:border-accent hover:text-accent">
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultItem({ hit, rank }: { hit: SearchHit; rank: number }) {
  const c = hit.citation;
  const copyCitation = () => {
    const text = `${c.regulator}, ${c.document_name} (${c.version}), ${c.location_label}${c.section_heading ? `, “${c.section_heading}”` : ""}`;
    navigator.clipboard?.writeText(text).then(() => toast.success("Citation copied"), () => toast.error("Clipboard not available"));
  };
  return (
    <li className="grid overflow-hidden rounded-lg bg-surface shadow-panel md:grid-cols-[1fr_250px]">
      <article className="min-w-0 px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-faint">
          <span className="tabular-nums">#{rank}</span>
          {hit.score !== null && <span title="BM25 relevance score">score {hit.score.toFixed(2)}</span>}
          {!hit.is_latest && <Tag tone="version" title="This paragraph is from a superseded version">Historical version</Tag>}
        </div>
        {hit.heading && (
          <h3 className="mb-2 font-serif text-[17px] font-semibold leading-snug text-ink">
            <SegmentText segments={hit.heading_segments} fallback={hit.heading} />
          </h3>
        )}
        <p className="reg-text whitespace-pre-line">
          <SegmentText segments={hit.text_segments} />
        </p>
        {hit.identical_text_in.length > 0 && (
          <p className="mt-3 text-xs text-muted">
            Identical text also appears in {hit.identical_text_in.map((d) => `${d.document_name} ${d.version} (${d.location_label})`).join("; ")}.
          </p>
        )}
      </article>
      <aside className="flex flex-col gap-3 border-t border-line bg-sunken/60 px-5 py-5 text-sm md:border-l md:border-t-0" aria-label="Citation">
        <div>
          <div className="font-semibold text-ink">{c.regulator}</div>
          <div className="mt-0.5 break-all text-muted">{c.document_name}</div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Tag tone="version">{c.version}</Tag>
          <Tag>{c.location_label}</Tag>
          <Tag>{c.source_type.toUpperCase()}</Tag>
        </div>
        {hit.effective_date && <div className="text-xs text-faint">Effective {formatDate(hit.effective_date)}</div>}
        {c.source_type !== "pdf" && (
          <p className="text-xs text-faint">{c.source_type === "html" ? "HTML has no page numbers; the link opens the section." : "Plain text has no pages; lines are cited instead."}</p>
        )}
        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          <Link to={c.viewer_url} className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90">
            <FileText className="h-4 w-4" aria-hidden /> View source
          </Link>
          <a href={c.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-muted hover:bg-surface hover:text-ink" aria-label="Open original file in a new tab">
            <ExternalLink className="h-4 w-4" />
          </a>
          <button onClick={copyCitation} className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-muted hover:bg-surface hover:text-ink" aria-label="Copy citation">
            <Copy className="h-4 w-4" />
          </button>
        </div>
      </aside>
    </li>
  );
}
