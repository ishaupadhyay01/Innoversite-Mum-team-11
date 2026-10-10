import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, EmptyState, ErrorState, Kv, Notice, PageHeader, Panel, Segmented, Select, SkeletonRows, StatusBadge, Tag, inputClass } from "../components/ui";
import { api } from "../services/api";
import type { ChecklistItem, GapResponse } from "../types/api";
import { displayValue, formatPercent } from "../utils/format";

export default function ChecklistPage() {
  const [view, setView] = useState<"checklist" | "gaps">("checklist");
  const [regulator, setRegulator] = useState("");
  const [tradeInput, setTradeInput] = useState("");
  const [tradeId, setTradeId] = useState<string | null>(null);
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });

  const checklist = useQuery({
    queryKey: ["checklist", regulator, tradeId],
    queryFn: () => api.checklist({ regulator: regulator ? [regulator] : [], trade_id: tradeId }),
    enabled: view === "checklist",
    retry: false,
  });

  const onTrade = (e: FormEvent) => {
    e.preventDefault();
    setTradeId(tradeInput.trim() || null);
  };

  return (
    <div>
      <PageHeader
        title="Compliance checklist"
        description="Rule-by-rule status for the whole dataset or for a single trade, plus a gap analysis that groups failures by type."
        actions={
          <Segmented
            label="View"
            value={view}
            onChange={setView}
            options={[
              { value: "checklist", label: "Checklist" },
              { value: "gaps", label: "Gap analysis" },
            ]}
          />
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Select
          label="Regulator"
          className="w-auto"
          value={regulator}
          onChange={setRegulator}
          options={[{ value: "", label: "All rule sets" }, ...(rules.data?.regulators ?? []).map((r) => ({ value: r, label: r }))]}
        />
        {view === "checklist" && (
          <form onSubmit={onTrade} className="flex gap-2">
            <input className={clsx(inputClass, "w-48")} placeholder="Trade ID, e.g. T000004" aria-label="Trade ID" value={tradeInput} onChange={(e) => setTradeInput(e.target.value)} />
            <Button type="submit" icon={<Search className="h-4 w-4" />}>Check trade</Button>
            {tradeId && (
              <Button type="button" variant="ghost" onClick={() => { setTradeId(null); setTradeInput(""); }}>
                Whole dataset
              </Button>
            )}
          </form>
        )}
      </div>

      {view === "checklist" ? (
        checklist.isLoading ? (
          <SkeletonRows rows={6} />
        ) : checklist.isError ? (
          <ErrorState error={checklist.error} onRetry={() => checklist.refetch()} />
        ) : checklist.data ? (
          <>
            {checklist.data.trade && (
              <Panel className="mb-5" title={`Trade ${tradeId}`}>
                <div className="grid gap-x-8 gap-y-1 text-sm sm:grid-cols-3">
                  {Object.entries(checklist.data.trade).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3 border-b border-line/60 py-1">
                      <span className="text-muted">{k}</span>
                      <span className={clsx(v === null && "italic text-faint")}>{displayValue(v)}</span>
                    </div>
                  ))}
                </div>
              </Panel>
            )}
            <div className="space-y-3">
              {checklist.data.items.map((item) => (
                <ChecklistCard key={item.rule_id} item={item} scope={checklist.data!.scope} />
              ))}
            </div>
            <p className="mt-4 text-xs text-faint">
              Evaluated live on {checklist.data.dataset} ({checklist.data.trades} trades) with the currently loaded rules. Results are deterministic for the same data and rules.
            </p>
          </>
        ) : null
      ) : (
        <GapAnalysis regulator={regulator} />
      )}
    </div>
  );
}

function ChecklistCard({ item, scope }: { item: ChecklistItem; scope: "dataset" | "trade" }) {
  return (
    <div className="grid gap-4 rounded-lg bg-surface p-5 shadow-panel md:grid-cols-[180px_1fr_auto]">
      <div>
        <div className="font-semibold">{item.rule_id}</div>
        <div className="text-sm text-muted">{item.regulator}</div>
        <div className="mt-2">
          <StatusBadge status={item.status} />
        </div>
      </div>
      <div className="min-w-0">
        <p className="font-medium text-ink">{item.description}</p>
        <p className="mt-1 text-sm text-muted">
          <span className="text-faint">Applicability:</span> {item.applicability}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink">{item.explanation}</p>
        <p className="mt-1.5 text-xs text-faint">Source: {item.rule_source}</p>
      </div>
      {scope === "dataset" && (
        <div className="grid grid-cols-4 gap-3 text-center text-sm md:w-72">
          <Count label="Pass" value={item.pass} tone="text-pass" />
          <Count label="Fail" value={item.fail} tone="text-fail" />
          <Count label="N/A" value={item.not_applicable} tone="text-na" />
          <Count label="Rate" value={formatPercent(item.compliance_rate, 0)} tone="text-ink" />
        </div>
      )}
    </div>
  );
}

function Count({ label, value, tone }: { label: string; value: number | string | undefined; tone: string }) {
  return (
    <div>
      <div className={clsx("text-lg font-semibold tabular-nums", tone)}>{value ?? "—"}</div>
      <div className="text-xs text-faint">{label}</div>
    </div>
  );
}

function GapAnalysis({ regulator }: { regulator: string }) {
  const [includeSchema, setIncludeSchema] = useState(true);
  const gap = useMutation({ mutationFn: () => api.gap({ regulators: regulator ? [regulator] : [], include_schema_validation: includeSchema }) });
  const data: GapResponse | undefined = gap.data;
  return (
    <div className="space-y-5">
      <Panel>
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="primary" loading={gap.isPending} onClick={() => gap.mutate()}>
            Run gap analysis
          </Button>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeSchema} onChange={(e) => setIncludeSchema(e.target.checked)} />
            Also validate against the reporting JSON Schema
          </label>
          <span className="text-sm text-muted">{regulator ? `Rule set: ${regulator}` : "All rule sets"}</span>
        </div>
      </Panel>
      {gap.isError && <ErrorState error={gap.error} />}
      {!data && !gap.isPending && !gap.isError && <EmptyState title="Gap analysis has not been run">It groups rule failures into missing values, invalid formats, disallowed values, negative numbers and other categories.</EmptyState>}
      {data && (
        <>
          <Notice>{data.notes.join(" ")}</Notice>
          <Panel title="Rule-based findings" description={`${data.rule_findings.total_failed_evaluations} failed evaluations affecting ${data.rule_findings.impacted_trades} of ${data.trades} trades, from rules ${data.rules_evaluated.join(", ")}`}>
            {data.rule_findings.by_category.length === 0 ? (
              <p className="text-sm text-muted">No rule failures.</p>
            ) : (
              <div className="space-y-4">
                {data.rule_findings.by_category.map((c) => (
                  <div key={c.category} className="rounded-md border border-line p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="font-semibold">{c.label}</h3>
                      <span className="text-sm text-muted">
                        {c.failed_evaluations} failures, {c.impacted_trades} trades
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {c.rule_ids.map((r) => <Tag key={r}>{r}</Tag>)}
                      {c.fields.map((f) => <Tag key={f} tone="accent">{f}</Tag>)}
                    </div>
                    <p className="mt-2 text-sm text-muted">Trades: {c.trade_ids.slice(0, 20).join(", ")}{c.impacted_trades > 20 ? ` and ${c.impacted_trades - 20} more` : ""}</p>
                    {c.examples[0] && <p className="mt-2 text-sm text-ink">Example, {c.examples[0].trade_id} / {c.examples[0].rule_id}: {c.examples[0].explanation}</p>}
                  </div>
                ))}
                <Kv
                  items={[
                    {
                      label: "Conditional requirements",
                      value: `${data.rule_findings.conditional_requirements.failed_evaluations} failures on ${data.rule_findings.conditional_requirements.impacted_trades} trades (rules ${data.rule_findings.conditional_requirements.rule_ids.join(", ") || "none"})`,
                    },
                  ]}
                />
              </div>
            )}
          </Panel>
          {data.schema_findings.enabled && (
            <Panel title="Reporting-schema findings" description={`${data.schema_findings.total} findings on ${data.schema_findings.impacted_trades ?? 0} trades from reporting_schema.json (independent of the rule files)`} padded={false}>
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs text-muted">
                  <tr>
                    <th className="px-5 py-2 font-medium">Field</th>
                    <th className="px-3 py-2 font-medium">Check</th>
                    <th className="px-3 py-2 font-medium">Count</th>
                    <th className="px-5 py-2 font-medium">Example</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.schema_findings.by_check.map((b) => (
                    <tr key={`${b.field}-${b.check}`}>
                      <td className="px-5 py-2 font-medium">{b.field}</td>
                      <td className="px-3 py-2">{b.check}</td>
                      <td className="px-3 py-2 tabular-nums">{b.count}</td>
                      <td className="px-5 py-2 text-muted">{b.example}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
