import { useQuery } from "@tanstack/react-query";
import { FileStack, GitCompareArrows, Play, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, Notice, Panel, Skeleton, Stat, StatusBadge, Tag } from "../components/ui";
import { useChartColors } from "../hooks/useChartColors";
import { api } from "../services/api";
import type { Alert } from "../types/api";
import { formatDate, formatNumber, formatPercent, relativeTime } from "../utils/format";

export default function DashboardPage() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 15_000 });
  const colors = useChartColors();

  if (q.isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const analysis = d.analysis;
  const s = analysis?.summary;
  const tooltipStyle = { background: colors.surface, border: `1px solid ${colors.line}`, borderRadius: 6, fontSize: 13, color: colors.ink };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Compliance overview</h1>
          <p className="mt-1.5 text-muted">
            {d.documents ? `${d.documents.versions} document versions from ${d.documents.regulators} regulators` : "Repository statistics unavailable"}
            {analysis && `, last impact analysis ${relativeTime(analysis.finished_at)}`}.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/search" className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm font-medium hover:bg-sunken">
            <Search className="h-4 w-4" /> Search regulations
          </Link>
          <Link to="/impact" className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-white hover:bg-accent/90">
            <Play className="h-4 w-4" /> Run impact analysis
          </Link>
        </div>
      </div>

      {d.errors.length > 0 && (
        <div className="mb-5">
          <Notice tone="warn">
            Some figures could not be loaded: {d.errors.join("; ")}
          </Notice>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Regulatory documents" value={formatNumber(d.documents?.documents)} hint={`${formatNumber(d.documents?.versions)} versions in total`} />
        <Stat label="Regulators" value={formatNumber(d.documents?.regulators)} hint={d.rules ? `${d.rules.total_rules} executable rules for ${d.rules.regulators.length} regimes` : undefined} />
        <Stat label="Indexed paragraphs" value={formatNumber(d.index?.paragraphs_total)} hint={d.index ? `${formatNumber(d.index.paragraphs_latest)} in latest versions` : "Search index unavailable"} />
        <Stat label="Unread updates" value={formatNumber(d.documents?.unread_alerts)} tone={d.documents?.unread_alerts ? "version" : undefined} hint="New documents and versions" />
        <Stat label="Trades analysed" value={formatNumber(s?.total_trades)} hint={analysis ? `${analysis.dataset}, ${s?.total_rules} rules` : "No analysis run yet"} />
        <Stat label="Non-compliant trades" value={formatNumber(s?.unique_impacted_trades)} tone={s?.unique_impacted_trades ? "fail" : undefined} hint={s ? `of ${s.total_trades} trades fail at least one rule` : undefined} />
        <Stat label="Rule violations" value={formatNumber(s?.status_counts.FAIL)} tone={s?.status_counts.FAIL ? "fail" : undefined} hint={s ? `${formatNumber(s.status_counts.NOT_APPLICABLE)} not applicable, ${s.status_counts.ERROR} errors` : undefined} />
        <Stat label="Fully compliant trades" value={formatPercent(s?.trade_compliance_rate)} tone={s ? "pass" : undefined} hint={s ? `${s.fully_compliant_trades} trades pass every applicable rule` : undefined} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="Violations by rule" description={analysis ? `Evaluation results from ${analysis.dataset}` : undefined}>
          {s ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={s.by_rule} margin={{ left: -12, right: 8, top: 8 }}>
                  <CartesianGrid vertical={false} stroke={colors.line} />
                  <XAxis dataKey="rule_id" tick={{ fill: colors.muted, fontSize: 12 }} axisLine={{ stroke: colors.line }} tickLine={false} />
                  <YAxis tick={{ fill: colors.muted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.line, opacity: 0.35 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="fail" name="Fail" stackId="a" fill={colors.fail} />
                  <Bar dataKey="pass" name="Pass" stackId="a" fill={colors.pass} />
                  <Bar dataKey="not_applicable" name="Not applicable" stackId="a" fill={colors.na} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No impact analysis yet" action={<Link className="text-sm font-medium text-accent hover:underline" to="/impact">Run the analysis</Link>}>
              Run the trade dataset against the JSON rule sets to see violations here.
            </EmptyState>
          )}
        </Panel>

        <Panel title="What's new" actions={<Link to="/whats-new" className="text-sm font-medium text-accent hover:underline">All updates</Link>} padded={false}>
          {d.alerts && d.alerts.items.length > 0 ? (
            <ul className="divide-y divide-line">
              {d.alerts.items.map((a) => (
                <AlertLine key={a.id} alert={a} />
              ))}
            </ul>
          ) : (
            <EmptyState title="No updates recorded" icon={<GitCompareArrows className="h-8 w-8" />}>Uploading a new document or version creates an update here.</EmptyState>
          )}
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Panel title="Impacted trades by regulator">
          {s ? (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={s.by_regulator} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke={colors.line} />
                  <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="regulator" tick={{ fill: colors.ink, fontSize: 12 }} axisLine={false} tickLine={false} width={70} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.line, opacity: 0.35 }} />
                  <Bar dataKey="impacted_trades" name="Trades with ≥1 failure" fill={colors.fail} radius={[0, 3, 3, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-muted">No analysis yet.</p>
          )}
        </Panel>

        <Panel title="Indexed paragraphs by regulator">
          {d.index && d.index.paragraphs_by_regulator.length ? (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.index.paragraphs_by_regulator} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke={colors.line} />
                  <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="regulator" tick={{ fill: colors.ink, fontSize: 12 }} axisLine={false} tickLine={false} width={80} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.line, opacity: 0.35 }} />
                  <Bar dataKey="paragraphs" name="Paragraphs (all versions)" fill={colors.accent} radius={[0, 3, 3, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="Index is empty" icon={<FileStack className="h-8 w-8" />}>The dataset import may still be running; see System health.</EmptyState>
          )}
        </Panel>

        <Panel title="Recent activity" padded={false}>
          {d.activity && d.activity.length ? (
            <ul className="scroll-thin max-h-56 divide-y divide-line overflow-y-auto">
              {d.activity.map((e) => (
                <li key={e.id} className="px-5 py-2.5 text-sm">
                  <p className="text-ink">{e.summary}</p>
                  <p className="text-xs text-faint">
                    {e.service}, {relativeTime(e.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="p-5 text-sm text-muted">No activity recorded yet.</p>
          )}
        </Panel>
      </div>

      {d.search && d.search.total_searches > 0 && (
        <Panel className="mt-6" title="Search activity" description={`Last ${d.search.window_days} days`}>
          <div className="grid gap-6 md:grid-cols-3">
            <div>
              <div className="text-sm text-muted">Searches</div>
              <div className="text-2xl font-semibold">{formatNumber(d.search.searches_in_window)}</div>
              <div className="mt-3 text-sm text-muted">Average response</div>
              <div className="text-2xl font-semibold">{d.search.avg_response_ms ?? "—"} ms</div>
              <div className="mt-3 text-sm text-muted">Searches with no results</div>
              <div className="text-2xl font-semibold">{formatPercent(d.search.zero_result_rate, 0)}</div>
            </div>
            <div className="md:col-span-2">
              <div className="mb-2 text-sm font-medium">Most frequent queries</div>
              <ul className="space-y-1.5 text-sm">
                {d.search.top_queries.map((t) => (
                  <li key={t.query} className="flex items-center justify-between gap-3">
                    <Link to={`/search?q=${encodeURIComponent(t.query)}`} className="truncate text-accent hover:underline">
                      {t.query}
                    </Link>
                    <span className="text-faint">
                      {t.count} searches, {t.avg_hits} hits on average
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}

function AlertLine({ alert }: { alert: Alert }) {
  return (
    <li className="px-5 py-3">
      <div className="flex items-start justify-between gap-3">
        <Link to={`/whats-new?alert=${alert.id}`} className="min-w-0 font-medium text-ink hover:text-accent">
          {alert.document_name}
        </Link>
        {!alert.is_read && <StatusBadge status="running" label="New" />}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <span>{alert.regulator}</span>
        {alert.previous_version_label ? (
          <Tag tone="version">
            {alert.previous_version_label} to {alert.new_version_label}
          </Tag>
        ) : (
          <Tag tone="version">{alert.new_version_label}</Tag>
        )}
        <span>effective {formatDate(alert.effective_date)}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-sm text-muted">{alert.summary}</p>
    </li>
  );
}
