import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { rulesApi } from "@/api/rules";
import type { ResultFilters } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, Stat } from "@/components/ui/Card";
import { ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { downloadFile } from "@/lib/download";
import { fmtDateTime, fmtInt, fmtPct } from "@/lib/format";
import { ImpactMatrixTable } from "./ImpactMatrixTable";

export function RunPage() {
  const { runId = "" } = useParams();
  const [filters, setFilters] = useState<ResultFilters>({ status: ["FAIL"], rule_code: [], regulator: [], asset_class: [] });
  const [exportError, setExportError] = useState<unknown>(null);
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => rulesApi.getRun(runId),
    refetchInterval: (q) => (q.state.data && ["QUEUED", "RUNNING"].includes(q.state.data.status) ? 1500 : false),
  });
  const done = run.data?.status === "COMPLETED";
  const stats = useQuery({ queryKey: ["run-stats", runId], queryFn: () => rulesApi.stats(runId), enabled: done });

  if (run.isLoading) return <Spinner />;
  if (run.error) return <ErrorBanner error={run.error} />;
  const r = run.data!;
  const s = stats.data;

  return (
    <>
      <PageHeader
        title="Impact Matrix"
        subtitle={`Run started ${fmtDateTime(r.created_at)} · ${fmtInt(r.total_trades)} trades × ${r.total_rules} rules`}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={r.status} />
            <Button variant="secondary" disabled={!done}
              onClick={() => downloadFile(rulesApi.exportUrl(runId, filters), `impact-matrix-${runId}.csv`).catch(setExportError)}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
          </div>
        }
      />
      <ErrorBanner error={exportError} />
      {!done && r.status !== "FAILED" && (
        <Card>
          <Spinner label={`Evaluating… chunk ${r.chunks_done} of ${r.chunks_total}`} />
        </Card>
      )}
      {r.status === "FAILED" && <ErrorBanner error={new Error(r.error_message ?? "Run failed")} />}
      {s && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Pass rate" value={fmtPct(s.pass_rate)} tone={s.pass_rate > 0.95 ? "pass" : "fail"} />
            <Stat label="Checks passed" value={fmtInt(s.passed)} tone="pass" />
            <Stat label="Checks failed" value={fmtInt(s.failed)} tone="fail" />
            <Stat label="Not applicable" value={fmtInt(s.not_applicable)} tone="na" />
            <Stat label="Trades needing action" value={`${fmtInt(s.trades_with_failures)} / ${fmtInt(s.total_trades)}`} />
          </div>
          <Card title="Failures by rule" className="mb-6">
            <div className="space-y-2">
              {s.by_rule.map((rule) => {
                const applicable = rule.passed + rule.failed;
                return (
                  <button key={rule.rule_code} className="grid w-full grid-cols-[110px_1fr_140px] items-center gap-3 text-left text-sm hover:opacity-80"
                    onClick={() => setFilters({ ...filters, status: ["FAIL"], rule_code: [rule.rule_code] })}>
                    <span className="font-mono text-xs font-medium">{rule.rule_code}</span>
                    <span className="flex h-3 overflow-hidden rounded bg-canvas" title={`${rule.failed} fail / ${rule.passed} pass / ${rule.not_applicable} n/a`}>
                      <span className="bg-fail" style={{ width: `${(rule.failed / Math.max(1, s.total_trades)) * 100}%` }} />
                      <span className="bg-pass/70" style={{ width: `${(rule.passed / Math.max(1, s.total_trades)) * 100}%` }} />
                    </span>
                    <span className="text-right font-mono text-xs text-ink-soft">
                      {rule.failed} fail{applicable ? ` · ${fmtPct(rule.fail_rate)}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>
          <ImpactMatrixTable runId={runId} stats={s} filters={filters} onFilters={setFilters} />
        </>
      )}
    </>
  );
}
