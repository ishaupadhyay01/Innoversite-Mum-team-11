import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import { rulesApi } from "@/api/rules";
import { PageHeader } from "@/components/layout/AppShell";
import { Card, Stat } from "@/components/ui/Card";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { StatusBadge } from "@/components/ui/Badge";
import { fmtDateTime, fmtInt } from "@/lib/format";
import { WhatsNewCard } from "./WhatsNewCard";

export function DashboardPage() {
  const [params] = useSearchParams();
  const highlighted = params.get("card");
  const stats = useQuery({ queryKey: ["ingestion-stats"], queryFn: ingestionApi.stats, refetchInterval: 15_000 });
  const cards = useQuery({ queryKey: ["whats-new"], queryFn: () => ingestionApi.whatsNew(1, 20), refetchInterval: 15_000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: rulesApi.listRuns });

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Regulatory changes and recent compliance analyses" />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Documents" value={stats.data ? fmtInt(stats.data.documents) : "–"} />
        <Stat label="Active versions" value={stats.data ? fmtInt(stats.data.active_versions) : "–"} />
        <Stat label="Processing" value={stats.data ? fmtInt(stats.data.processing) : "–"} />
        <Stat label="Failed parses" value={stats.data ? fmtInt(stats.data.failed) : "–"} tone={stats.data?.failed ? "fail" : undefined} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">What's new</h2>
          <ErrorBanner error={cards.error} />
          {cards.isLoading && <Spinner />}
          {cards.data?.items.length === 0 && (
            <EmptyState title="No regulatory updates yet">
              <Link to="/documents" className="text-brand hover:underline">Upload a regulation</Link> to see What's New cards.
            </EmptyState>
          )}
          <div className="space-y-3">
            {cards.data?.items.map((c) => <WhatsNewCard key={c.id} card={c} highlighted={c.id === highlighted} />)}
          </div>
        </div>
        <Card title="Recent impact runs" actions={<Link to="/impact" className="text-xs text-brand hover:underline">New analysis</Link>}>
          {runs.data?.length === 0 && <p className="text-sm text-ink-soft">No runs yet.</p>}
          <ul className="divide-y divide-line">
            {runs.data?.slice(0, 8).map((r) => (
              <li key={r.id} className="py-2">
                <Link to={`/impact/runs/${r.id}`} className="flex items-center justify-between gap-2 text-sm hover:underline">
                  <span>{fmtDateTime(r.created_at)}</span>
                  <StatusBadge status={r.status} />
                </Link>
                {r.status === "COMPLETED" && (
                  <div className="mt-0.5 font-mono text-xs text-ink-soft">
                    {fmtInt(r.summary.failed ?? 0)} fail · {fmtInt(r.summary.trades_with_failures ?? 0)}/{fmtInt(r.total_trades)} trades affected
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
