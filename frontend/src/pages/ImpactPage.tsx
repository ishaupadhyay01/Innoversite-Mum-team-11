import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, Download, Play } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import {
  Button,
  CheckList,
  Code,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  JsonBlock,
  Kv,
  Notice,
  PageHeader,
  Pagination,
  Panel,
  Select,
  SkeletonRows,
  Stat,
  StatusBadge,
  Tag,
  inputClass,
} from "../components/ui";
import { useChartColors } from "../hooks/useChartColors";
import { useDebounce } from "../hooks/useDebounce";
import { ApiError, api, downloadFile } from "../services/api";
import type { AnalysisRun, EvalStatus, ImpactRow, TradeVerdict } from "../types/api";
import { displayValue, formatDateTime, formatNumber, formatPercent } from "../utils/format";

type SortKey = "seq" | "trade_id" | "asset_class" | "regulator" | "rule_id" | "status";

export default function ImpactPage() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const runs = useQuery({ queryKey: ["analyses"], queryFn: api.analyses });
  const [dataset, setDataset] = useState("");
  const [regulators, setRegulators] = useState<string[]>([]);
  const [ruleIds, setRuleIds] = useState<string[]>([]);
  const [analysisId, setAnalysisId] = useState<string | null>(null);

  useEffect(() => {
    if (!dataset && datasets.data?.length) setDataset(datasets.data.find((d) => d.default)?.name ?? datasets.data[0].name);
  }, [datasets.data, dataset]);
  useEffect(() => {
    if (!analysisId && runs.data) setAnalysisId(runs.data.find((r) => r.status === "completed")?.id ?? null);
  }, [runs.data, analysisId]);

  const run = useMutation({
    mutationFn: () => api.runAnalysis({ dataset, regulators, rule_ids: ruleIds }),
    onSuccess: (res: AnalysisRun) => {
      setAnalysisId(res.id);
      toast.success("Impact analysis complete", {
        description: `${res.summary.status_counts.FAIL} violations across ${res.summary.unique_impacted_trades} trades`,
      });
      qc.invalidateQueries({ queryKey: ["analyses"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Analysis failed"),
  });

  const allRules = (rules.data?.rule_sets ?? []).flatMap((rs) => rs.rules);
  const visibleRules = regulators.length ? allRules.filter((r) => regulators.includes(r.regulator)) : allRules;
  // Rule order follows the rule files, so the expression reads the same way as the results.
  const andExpression = visibleRules.filter((r) => ruleIds.includes(r.id)).map((r) => r.id).join(" AND ");

  return (
    <div>
      <PageHeader
        title="Impact analysis"
        description="Evaluates every trade in a synthetic dataset against the JSON rule sets. Each cell of the Impact Matrix records the status, the failing condition and the actual field values."
      />

      <Panel className="mb-6" title="Run an analysis">
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr_1.4fr_auto]">
          <Field label="Trade dataset">
            <Select
              label="Trade dataset"
              value={dataset}
              onChange={setDataset}
              options={(datasets.data ?? []).map((d) => ({ value: d.name, label: `${d.name} (${d.trades} trades)` }))}
            />
          </Field>
          <div>
            <div className="mb-1.5 text-sm font-medium">Regulations</div>
            <CheckList
              options={(rules.data?.regulators ?? []).map((r) => ({ value: r, count: allRules.filter((x) => x.regulator === r).length }))}
              selected={regulators}
              onToggle={(v) => setRegulators((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]))}
            />
            <p className="mt-1 text-xs text-faint">None selected means all.</p>
          </div>
          <div>
            <div className="mb-1.5 text-sm font-medium">Rules (combined with AND)</div>
            <div className="scroll-thin max-h-40 overflow-y-auto">
              <CheckList
                options={visibleRules.map((r) => ({ value: r.id, label: `${r.id}: ${r.description}` }))}
                selected={ruleIds}
                onToggle={(v) => setRuleIds((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]))}
              />
            </div>
            <p className="mt-1 text-xs text-faint">
              A trade is compliant only if it satisfies <strong className="font-medium text-muted">every</strong> selected rule
              {andExpression ? <> (<span className="font-mono">{andExpression}</span>)</> : <> — none selected means all {visibleRules.length} rules shown</>}.
            </p>
          </div>
          <div className="flex items-end">
            <Button variant="primary" size="lg" loading={run.isPending} icon={<Play className="h-4 w-4" />} onClick={() => run.mutate()} disabled={!dataset}>
              {run.isPending ? "Evaluating rules…" : "Run impact analysis"}
            </Button>
          </div>
        </div>
        {(runs.data?.length ?? 0) > 0 && (
          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4 text-sm">
            <span className="text-muted">Showing</span>
            <Select
              label="Analysis run"
              className="w-auto"
              value={analysisId ?? ""}
              onChange={(v) => setAnalysisId(v)}
              options={(runs.data ?? []).map((r) => ({
                value: r.id,
                label: `${formatDateTime(r.finished_at ?? r.started_at)}, ${r.dataset}, ${r.regulators.length ? r.regulators.join(", ") : "all regulators"} (${r.status})`,
              }))}
            />
          </div>
        )}
      </Panel>

      {analysisId ? <AnalysisView id={analysisId} /> : runs.isLoading ? <SkeletonRows /> : (
        <EmptyState title="No analysis has been run yet" action={<Button variant="primary" onClick={() => run.mutate()} loading={run.isPending}>Run impact analysis</Button>}>
          The analysis evaluates {datasets.data?.[0]?.trades ?? "the"} trades against {allRules.length} JSON rules.
        </EmptyState>
      )}
    </div>
  );
}

function AnalysisView({ id }: { id: string }) {
  const colors = useChartColors();
  const [status, setStatus] = useState<EvalStatus | "">("FAIL");
  const [regulator, setRegulator] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [assetClass, setAssetClass] = useState("");
  const [tradeSearch, setTradeSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("seq");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<ImpactRow | null>(null);
  const trade = useDebounce(tradeSearch, 250);
  useEffect(() => setPage(1), [id, status, regulator, ruleId, assetClass, trade, sortBy, sortDir]);

  const filters = {
    status: status ? [status] : [],
    regulator: regulator ? [regulator] : [],
    rule_id: ruleId ? [ruleId] : [],
    asset_class: assetClass ? [assetClass] : [],
    trade_id: trade,
  };
  const matrix = useQuery({
    queryKey: ["matrix", id, filters, sortBy, sortDir, page],
    queryFn: () => api.matrix(id, { ...filters, sort_by: sortBy, sort_dir: sortDir, page, page_size: 25 }),
    placeholderData: keepPreviousData,
  });

  const exportCsv = async (scoped: boolean) => {
    try {
      await downloadFile(api.exportUrl(id, scoped ? filters : {}), "impact_matrix.csv");
      toast.success("Impact Matrix exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  };

  if (matrix.isLoading) return <SkeletonRows rows={6} />;
  if (matrix.isError) return <ErrorState error={matrix.error} onRetry={() => matrix.refetch()} />;
  const data = matrix.data!;
  const run = data.analysis;
  if (run.status === "failed") return <ErrorState error={new Error(run.error ?? "Analysis failed")} />;
  const s = run.summary;
  const tooltipStyle = { background: colors.surface, border: `1px solid ${colors.line}`, borderRadius: 6, fontSize: 13, color: colors.ink };

  const sortHeader = (key: SortKey, label: string) => (
    <th className="px-3 py-2.5 font-medium">
      <button
        className="inline-flex items-center gap-1 hover:text-ink"
        onClick={() => {
          if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
          else {
            setSortBy(key);
            setSortDir("asc");
          }
        }}
        aria-label={`Sort by ${label}`}
      >
        {label}
        {sortBy === key && (sortDir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </button>
    </th>
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Stat label="Trades analysed" value={formatNumber(s.total_trades)} />
        <Stat label="Rules evaluated" value={formatNumber(s.total_rules)} hint={`${formatNumber(s.total_evaluations)} evaluations`} />
        <Stat label="Failed" value={formatNumber(s.status_counts.FAIL)} tone="fail" />
        <Stat label="Passed" value={formatNumber(s.status_counts.PASS)} tone="pass" />
        <Stat label="Not applicable" value={formatNumber(s.status_counts.NOT_APPLICABLE)} hint={s.status_counts.ERROR ? `${s.status_counts.ERROR} evaluation errors` : "0 evaluation errors"} />
        <Stat label="Impacted trades" value={formatNumber(s.unique_impacted_trades)} tone="fail" hint={`${formatPercent(s.trade_compliance_rate)} fully compliant`} />
      </div>
      {(s.dataset_warnings?.length ?? 0) > 0 && <Notice tone="warn">Dataset warnings: {s.dataset_warnings!.join("; ")}</Notice>}

      <TradeVerdicts
        id={id}
        onShowTrade={(tradeId) => {
          setTradeSearch(tradeId);
          setStatus("");
          setRegulator("");
          setRuleId("");
          setAssetClass("");
          document.getElementById("impact-matrix")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Failures by regulator">
          <MiniBars data={s.by_regulator.map((r) => ({ name: r.regulator, value: r.fail }))} color={colors.fail} colors={colors} tooltipStyle={tooltipStyle} />
        </Panel>
        <Panel title="Impacted trades by asset class">
          <MiniBars data={s.by_asset_class.map((r) => ({ name: r.asset_class, value: r.impacted_trades }))} color={colors.warn} colors={colors} tooltipStyle={tooltipStyle} />
        </Panel>
        <Panel title="Failures by type">
          <ul className="space-y-2 text-sm">
            {s.by_category.map((c) => (
              <li key={c.category} className="flex items-center justify-between gap-3">
                <span className="text-ink">{c.label}</span>
                <span className="tabular-nums text-muted">{c.count}</span>
              </li>
            ))}
            {s.by_category.length === 0 && <li className="text-muted">No failures.</li>}
          </ul>
        </Panel>
      </div>

      <Panel
        id="impact-matrix"
        title="Impact Matrix"
        description={`Run ${run.id.slice(0, 8)} on ${run.dataset}, finished ${formatDateTime(run.finished_at)} in ${run.duration_ms ?? "—"} ms`}
        padded={false}
        actions={
          <>
            <Button size="sm" icon={<Download className="h-4 w-4" />} onClick={() => exportCsv(true)}>
              Export filtered CSV
            </Button>
            <Button size="sm" variant="ghost" onClick={() => exportCsv(false)}>
              Full CSV
            </Button>
            <Button size="sm" variant="ghost" onClick={() => downloadFile(api.summaryExportUrl(id), "impact_summary.csv").catch((e) => toast.error(String(e)))}>
              Summary CSV
            </Button>
          </>
        }
      >
        <div className="flex flex-wrap gap-3 border-b border-line px-5 py-3.5">
          <input className={clsx(inputClass, "w-44")} placeholder="Trade ID" aria-label="Search by Trade ID" value={tradeSearch} onChange={(e) => setTradeSearch(e.target.value)} />
          <Select
            label="Status"
            className="w-auto"
            value={status}
            onChange={(v) => setStatus(v as EvalStatus | "")}
            options={[
              { value: "", label: "All statuses" },
              { value: "FAIL", label: "Fail" },
              { value: "PASS", label: "Pass" },
              { value: "NOT_APPLICABLE", label: "Not applicable" },
              { value: "ERROR", label: "Error" },
            ]}
          />
          <Select label="Regulator" className="w-auto" value={regulator} onChange={setRegulator} options={[{ value: "", label: "All regulators" }, ...s.by_regulator.map((r) => ({ value: r.regulator, label: r.regulator }))]} />
          <Select label="Rule" className="w-auto" value={ruleId} onChange={setRuleId} options={[{ value: "", label: "All rules" }, ...s.by_rule.map((r) => ({ value: r.rule_id, label: r.rule_id }))]} />
          <Select label="Asset class" className="w-auto" value={assetClass} onChange={setAssetClass} options={[{ value: "", label: "All asset classes" }, ...s.by_asset_class.map((r) => ({ value: r.asset_class, label: r.asset_class }))]} />
          <span className="ml-auto self-center text-sm text-muted">
            {formatNumber(data.total)} rows, {formatNumber(data.distinct_trades)} trades
          </span>
        </div>
        {data.items.length === 0 ? (
          <EmptyState title="No rows match these filters">Change the status or filters to see other evaluations.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs text-muted">
                <tr>
                  {sortHeader("trade_id", "Trade ID")}
                  {sortHeader("asset_class", "Asset class")}
                  {sortHeader("regulator", "Regulator")}
                  {sortHeader("rule_id", "Rule")}
                  {sortHeader("status", "Status")}
                  <th className="px-3 py-2.5 font-medium">Field</th>
                  <th className="px-3 py-2.5 font-medium">Explanation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((r) => (
                  <tr key={r.id} className="cursor-pointer align-top hover:bg-sunken/60" onClick={() => setSelected(r)}>
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium">
                      <button className="hover:text-accent" onClick={(e) => { e.stopPropagation(); setSelected(r); }}>
                        {r.trade_id}
                      </button>
                    </td>
                    <td className="px-3 py-2.5">{r.asset_class}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">{r.regulator}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">{r.rule_id}</td>
                    <td className="px-3 py-2.5"><StatusBadge status={r.status} /></td>
                    <td className="px-3 py-2.5">{r.affected_fields.join(", ") || "—"}</td>
                    <td className="max-w-[46ch] px-3 py-2.5 text-muted">{r.explanation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-line px-5 py-3">
          <Pagination page={page} totalPages={data.total_pages} total={data.total} onChange={setPage} label="rows" />
        </div>
      </Panel>

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected ? `${selected.trade_id}, ${selected.rule_id}` : ""}>
        {selected && <ResultDetail analysisId={id} rowId={selected.id} />}
      </Drawer>
    </div>
  );
}

const OVERALL_LABEL: Record<string, string> = {
  FAIL: "Non-compliant",
  PASS: "Compliant",
  NOT_APPLICABLE: "No rule applies",
  ERROR: "Undetermined",
};

/** One verdict per trade: the run's selected rules combined with AND. */
function TradeVerdicts({ id, onShowTrade }: { id: string; onShowTrade: (tradeId: string) => void }) {
  const [overall, setOverall] = useState<EvalStatus | "">("FAIL");
  const [tradeSearch, setTradeSearch] = useState("");
  const [page, setPage] = useState(1);
  const trade = useDebounce(tradeSearch, 250);
  useEffect(() => setPage(1), [id, overall, trade]);
  const filters = { overall: overall ? [overall] : [], trade_id: trade };
  const verdicts = useQuery({
    queryKey: ["trade-verdicts", id, filters, page],
    queryFn: () => api.tradeVerdicts(id, { ...filters, page, page_size: 10 }),
    placeholderData: keepPreviousData,
  });

  const exportCsv = async () => {
    try {
      await downloadFile(api.tradeVerdictExportUrl(id, filters), "trade_verdicts.csv");
      toast.success("Trade verdicts exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  };

  if (verdicts.isLoading) return <SkeletonRows rows={4} />;
  if (verdicts.isError) return <ErrorState error={verdicts.error} onRetry={() => verdicts.refetch()} />;
  const data = verdicts.data!;
  const c = data.combined;

  return (
    <Panel
      title="Trade verdicts: selected rules combined with AND"
      description={`A trade is compliant only if it satisfies every selected rule (${c.rule_ids.length} rules: ${c.expression}). A rule that does not apply to a trade, such as a derivatives-only rule on an equity, counts as satisfied.`}
      padded={false}
      actions={
        <Button size="sm" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
          Export CSV
        </Button>
      }
    >
      <div className="grid gap-4 border-b border-line px-5 py-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Compliant trades" value={formatNumber(c.compliant_trades)} tone="pass" hint={`${formatPercent(c.compliance_rate)} pass all selected rules`} />
        <Stat label="Non-compliant trades" value={formatNumber(c.non_compliant_trades)} tone="fail" hint="fail at least one selected rule" />
        <Stat label="Undetermined" value={formatNumber(c.undetermined_trades)} hint="a rule could not be evaluated" />
        <Stat label="Trades" value={formatNumber(c.trades)} hint={c.status_counts.NOT_APPLICABLE ? `${c.status_counts.NOT_APPLICABLE} with no applicable rule` : "evaluated against every selected rule"} />
      </div>
      <div className="flex flex-wrap gap-3 border-b border-line px-5 py-3.5">
        <input className={clsx(inputClass, "w-44")} placeholder="Trade ID" aria-label="Search trade verdicts by Trade ID" value={tradeSearch} onChange={(e) => setTradeSearch(e.target.value)} />
        <Select
          label="Overall result"
          className="w-auto"
          value={overall}
          onChange={(v) => setOverall(v as EvalStatus | "")}
          options={[
            { value: "", label: "All trades" },
            { value: "FAIL", label: "Non-compliant" },
            { value: "PASS", label: "Compliant" },
            { value: "ERROR", label: "Undetermined" },
            { value: "NOT_APPLICABLE", label: "No rule applies" },
          ]}
        />
        <span className="ml-auto self-center text-sm text-muted">{formatNumber(data.total)} trades</span>
      </div>
      {data.items.length === 0 ? (
        <EmptyState title="No trades match these filters">Change the overall result filter to see other trades.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs text-muted">
              <tr>
                <th className="px-3 py-2.5 font-medium">Trade ID</th>
                <th className="px-3 py-2.5 font-medium">Asset class</th>
                <th className="px-3 py-2.5 font-medium">Overall (AND)</th>
                <th className="px-3 py-2.5 font-medium">Failed rules</th>
                <th className="px-3 py-2.5 font-medium">Why</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((v: TradeVerdict) => (
                <tr key={v.trade_id} className="align-top">
                  <td className="whitespace-nowrap px-3 py-2.5 font-medium">
                    <button className="hover:text-accent" title="Show this trade's rows in the Impact Matrix" onClick={() => onShowTrade(v.trade_id)}>
                      {v.trade_id}
                    </button>
                  </td>
                  <td className="px-3 py-2.5">{v.asset_class ?? "—"}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={v.overall} label={OVERALL_LABEL[v.overall]} /></td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {v.failed_rule_ids.map((r) => <Tag key={r} tone="warn">{r}</Tag>)}
                      {v.error_rule_ids.map((r) => <Tag key={r} title="Could not be evaluated">{r} (error)</Tag>)}
                      {v.failed_rule_ids.length + v.error_rule_ids.length === 0 && <span className="text-muted">—</span>}
                    </div>
                  </td>
                  <td className="max-w-[60ch] px-3 py-2.5 text-muted">
                    {v.reason}
                    {v.failures.length > 0 && (
                      <ul className="mt-1 space-y-0.5 text-xs">
                        {v.failures.map((f) => (
                          <li key={f.rule_id}>
                            <span className="font-medium text-ink">{f.rule_id}:</span> {f.explanation}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="border-t border-line px-5 py-3">
        <Pagination page={page} totalPages={data.total_pages} total={data.total} onChange={setPage} label="trades" />
      </div>
    </Panel>
  );
}

function MiniBars({ data, color, colors, tooltipStyle }: { data: { name: string; value: number }[]; color: string; colors: ReturnType<typeof useChartColors>; tooltipStyle: CSSProperties }) {
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 16 }}>
          <CartesianGrid horizontal={false} stroke={colors.line} />
          <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fill: colors.ink, fontSize: 12 }} axisLine={false} tickLine={false} width={84} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.line, opacity: 0.35 }} />
          <Bar dataKey="value" name="Count" fill={color} radius={[0, 3, 3, 0]} barSize={16} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ResultDetail({ analysisId, rowId }: { analysisId: string; rowId: number }) {
  const q = useQuery({ queryKey: ["matrix-row", analysisId, rowId], queryFn: () => api.matrixRow(analysisId, rowId) });
  if (q.isLoading) return <SkeletonRows rows={5} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const { result, trade, rule, related_text } = q.data!;
  return (
    <div className="space-y-6">
      <section>
        <div className="mb-2 flex items-center gap-2">
          <StatusBadge status={result.status} />
          {result.category && <Tag>{result.category.replace(/_/g, " ")}</Tag>}
          {result.conditional && <Tag tone="version">Conditional requirement</Tag>}
        </div>
        <p className="text-[15px] leading-relaxed text-ink">{result.explanation}</p>
      </section>

      <section>
        <h3 className="mb-2 font-semibold">Evaluation</h3>
        <Kv
          items={[
            { label: "Rule", value: `${result.rule_id}: ${result.rule_description}` },
            { label: "Expected condition", value: <Code>{result.expected_condition || "—"}</Code> },
            {
              label: "Actual value",
              value: Object.keys(result.actual_values).length ? (
                <ul className="space-y-0.5">
                  {Object.entries(result.actual_values).map(([k, v]) => (
                    <li key={k}>
                      <span className="text-muted">{k}</span> = <span className={clsx(v === null && "italic text-fail")}>{displayValue(v)}</span>
                    </li>
                  ))}
                </ul>
              ) : "—",
            },
            { label: "Rule source", value: <Code>{result.rule_source}</Code> },
          ]}
        />
      </section>

      {trade && (
        <section>
          <h3 className="mb-2 font-semibold">Trade record</h3>
          <div className="overflow-hidden rounded-md border border-line">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {Object.entries(trade).map(([k, v]) => (
                  <tr key={k} className={clsx(result.affected_fields.includes(k) && "bg-fail-soft/60")}>
                    <th className="w-44 px-3 py-1.5 text-left font-normal text-muted">{k}</th>
                    <td className={clsx("px-3 py-1.5", v === null && "italic text-faint")}>{displayValue(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {rule && (
        <section>
          <h3 className="mb-2 font-semibold">Rule configuration</h3>
          <Kv
            items={[
              { label: "Logic", value: <Code>{rule.logic_text}</Code> },
              ...(rule.applies_when_text
                ? [{ label: "Applies when", value: <span><Code>{rule.applies_when_text}</Code> <span className="text-xs text-faint">({rule.applies_when_source === "overlay" ? "declared in rules_overlay.json" : "declared in the rule"})</span></span> }]
                : []),
              { label: "Impact text", value: rule.impact ?? "—" },
              { label: "Severity", value: rule.severity ?? "Not defined in the rule file" },
            ]}
          />
          {rule.applies_when_rationale && <p className="mt-2 text-sm text-muted">Applicability rationale: {rule.applies_when_rationale}</p>}
          {rule.normalization_notes.length > 0 && (
            <div className="mt-3">
              <Notice>
                <p className="mb-1 font-medium">Normalisation applied when loading this rule</p>
                <ul className="list-disc pl-5 text-sm">
                  {rule.normalization_notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </Notice>
            </div>
          )}
          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-muted">Original JSON from {rule.source_file}</summary>
            <div className="mt-2"><JsonBlock value={rule.source_logic} /></div>
          </details>
        </section>
      )}

      <section>
        <h3 className="mb-1 font-semibold">Document citation</h3>
        {rule?.citation ? (
          <JsonBlock value={rule.citation} />
        ) : (
          <p className="text-sm text-muted">
            The rule file has no document citation, so the authoritative source is <Code>{result.rule_source}</Code>.
          </p>
        )}
        {related_text.items.length > 0 && (
          <div className="mt-3">
            <p className="mb-2 text-sm text-muted">Related text found by keyword search in {result.regulator} documents (informational, not an authoritative mapping):</p>
            <ul className="space-y-2">
              {related_text.items.map((r) => (
                <li key={r.paragraph_id} className="rounded-md border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span className="font-medium text-ink">{r.document_name}</span>
                    <Tag tone="version">{r.version}</Tag>
                    <span>{r.location_label}</span>
                    <Link to={r.viewer_url} className="ml-auto text-accent hover:underline">View source</Link>
                  </div>
                  {r.heading && <p className="mt-1.5 font-serif text-sm font-semibold">{r.heading}</p>}
                  <p className="mt-1 font-serif text-sm leading-relaxed text-ink">{r.excerpt}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
        {related_text.status !== "ok" && related_text.status !== "not_computed" && (
          <p className="mt-2 text-xs text-warn">Related text lookup unavailable: {related_text.detail}</p>
        )}
      </section>
    </div>
  );
}
