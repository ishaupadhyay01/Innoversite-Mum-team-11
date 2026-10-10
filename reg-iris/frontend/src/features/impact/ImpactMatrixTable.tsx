import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { rulesApi } from "@/api/rules";
import type { ResultFilters, ResultStatus, RunStats } from "@/api/types";
import { StatusBadge } from "@/components/ui/Badge";
import { ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { useDebounce } from "@/lib/useDebounce";

const STATUSES: ResultStatus[] = ["FAIL", "PASS", "NOT_APPLICABLE", "ERROR"];

export function ImpactMatrixTable({ runId, stats, filters, onFilters }: {
  runId: string;
  stats?: RunStats;
  filters: ResultFilters;
  onFilters: (f: ResultFilters) => void;
}) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ col: string; desc: boolean }>({ col: "row_number", desc: false });
  const [tradeQuery, setTradeQuery] = useState(filters.trade_id ?? "");
  const debouncedTrade = useDebounce(tradeQuery);
  const effective = { ...filters, trade_id: debouncedTrade || undefined };
  const results = useQuery({
    queryKey: ["results", runId, effective, page, sort],
    queryFn: () => rulesApi.results(runId, effective, page, 50, sort.col, sort.desc),
    placeholderData: (prev) => prev,
  });
  const update = (f: Partial<ResultFilters>) => {
    setPage(1);
    onFilters({ ...filters, ...f });
  };
  const header = (col: string, label: string) => (
    <th className="th cursor-pointer select-none" onClick={() => setSort((s) => ({ col, desc: s.col === col ? !s.desc : false }))}>
      {label} {sort.col === col ? (sort.desc ? "↓" : "↑") : ""}
    </th>
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <label key={s} className="flex items-center gap-1.5 rounded-md border border-line bg-white px-2 py-1 text-sm">
            <input type="checkbox" checked={filters.status.includes(s)}
              onChange={(e) => update({ status: e.target.checked ? [...filters.status, s] : filters.status.filter((x) => x !== s) })} />
            <StatusBadge status={s} />
          </label>
        ))}
        <select className="input w-auto" value={filters.rule_code[0] ?? ""} onChange={(e) => update({ rule_code: e.target.value ? [e.target.value] : [] })} aria-label="Rule">
          <option value="">All rules</option>
          {stats?.by_rule.map((r) => <option key={r.rule_code} value={r.rule_code}>{r.rule_code}</option>)}
        </select>
        <select className="input w-auto" value={filters.regulator[0] ?? ""} onChange={(e) => update({ regulator: e.target.value ? [e.target.value] : [] })} aria-label="Regulator">
          <option value="">All regulators</option>
          {Object.keys(stats?.by_regulator ?? {}).map((r) => <option key={r}>{r}</option>)}
        </select>
        <select className="input w-auto" value={filters.asset_class[0] ?? ""} onChange={(e) => update({ asset_class: e.target.value ? [e.target.value] : [] })} aria-label="Asset class">
          <option value="">All asset classes</option>
          {Object.keys(stats?.by_asset_class ?? {}).map((r) => <option key={r}>{r}</option>)}
        </select>
        <input className="input w-44" placeholder="Trade ID…" value={tradeQuery} onChange={(e) => { setTradeQuery(e.target.value); setPage(1); }} />
      </div>
      <ErrorBanner error={results.error} />
      {results.isLoading && <Spinner />}
      {results.data && (
        <div className="overflow-x-auto rounded-lg border border-line bg-white">
          <table className="w-full">
            <thead>
              <tr>
                {header("trade_id", "Trade")}
                <th className="th">Asset</th>
                {header("rule_code", "Rule")}
                {header("status", "Result")}
                <th className="th">Explanation</th>
                <th className="th">Source</th>
              </tr>
            </thead>
            <tbody>
              {results.data.items.map((r) => (
                <tr key={r.id} className={r.status === "FAIL" ? "bg-fail-tint/30" : undefined}>
                  <td className="td font-mono text-xs">{r.trade_id}<div className="text-ink-faint">row {r.row_number}</div></td>
                  <td className="td text-xs">{r.asset_class}</td>
                  <td className="td whitespace-nowrap text-xs"><span className="font-mono font-medium">{r.rule_code}</span><div className="text-ink-faint">{r.regulator} · {r.severity}</div></td>
                  <td className="td"><StatusBadge status={r.status} /></td>
                  <td className="td max-w-xl text-xs leading-relaxed">{r.explanation}</td>
                  <td className="td text-xs text-ink-soft">{r.citation_label ?? r.clause_ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3">
            <Pagination page={page} pages={results.data.pages} total={results.data.total} onPage={setPage} />
          </div>
        </div>
      )}
    </div>
  );
}
