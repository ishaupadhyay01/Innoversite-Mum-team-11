import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BellOff, CheckCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, EmptyState, ErrorState, PageHeader, Pagination, Panel, Segmented, SkeletonRows, Tag, inputClass } from "../components/ui";
import { useDebounce } from "../hooks/useDebounce";
import { api } from "../services/api";
import { formatDate, relativeTime } from "../utils/format";

export default function AlertsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounce(q, 250);
  useEffect(() => setPage(1), [filter, debounced]);

  const alerts = useQuery({
    queryKey: ["alerts", "center", filter, debounced, page],
    queryFn: () => api.alerts({ unread_only: filter === "unread", q: debounced, page, page_size: 20 }),
    refetchInterval: 5000,
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  const mark = useMutation({ mutationFn: ({ id, read }: { id: number; read: boolean }) => api.markAlert(id, read), onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: api.readAll, onSuccess: invalidate });

  return (
    <div>
      <PageHeader
        title="Alert center"
        description="Notifications created when a document or version is added. The counter refreshes every few seconds."
        actions={
          <Button icon={<CheckCheck className="h-4 w-4" />} loading={readAll.isPending} onClick={() => readAll.mutate()} disabled={!alerts.data?.unread}>
            Mark all read
          </Button>
        }
      />
      <Panel padded={false}>
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3.5">
          <Segmented
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "unread", label: `Unread${alerts.data ? ` (${alerts.data.unread})` : ""}` },
            ]}
          />
          <input className={clsx(inputClass, "max-w-xs")} placeholder="Search alert history" aria-label="Search alert history" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {alerts.isLoading && <div className="p-5"><SkeletonRows /></div>}
        {alerts.isError && <div className="p-5"><ErrorState error={alerts.error} onRetry={() => alerts.refetch()} /></div>}
        {alerts.data && alerts.data.items.length === 0 && (
          <EmptyState title={filter === "unread" ? "No unread alerts" : "No alerts"} icon={<BellOff className="h-8 w-8" />}>
            Upload a new version from the Documents page to generate one.
          </EmptyState>
        )}
        {alerts.data && alerts.data.items.length > 0 && (
          <ul className="divide-y divide-line">
            {alerts.data.items.map((a) => (
              <li key={a.id} className={clsx("flex flex-wrap items-start gap-4 px-5 py-4", !a.is_read && "bg-version-soft/40")}>
                <span className={clsx("mt-2 h-2 w-2 flex-none rounded-full", a.is_read ? "bg-transparent" : "bg-version")} aria-label={a.is_read ? "Read" : "Unread"} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/whats-new?alert=${a.id}`} className="font-medium text-ink hover:text-accent">
                      {a.title}
                    </Link>
                    {a.change_types.map((c) => <Tag key={c} tone={c.startsWith("New") ? "version" : "neutral"}>{c}</Tag>)}
                  </div>
                  <p className="mt-1 text-sm text-muted">{a.summary}</p>
                  <p className="mt-1 text-xs text-faint">
                    Effective {formatDate(a.effective_date)}, recorded {relativeTime(a.event_time)}
                    {a.source === "initial_import" ? " (from the dataset's original upload timestamp)" : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  {a.previous_version_id && (
                    <Link to={`/compare?base=${a.previous_version_id}&target=${a.version_id}`} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-sunken">
                      View diff
                    </Link>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => mark.mutate({ id: a.id, read: !a.is_read })}>
                    {a.is_read ? "Mark unread" : "Mark read"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {alerts.data && (
          <div className="border-t border-line px-5 py-3">
            <Pagination page={page} totalPages={Math.ceil(alerts.data.total / alerts.data.page_size)} total={alerts.data.total} onChange={setPage} label="alerts" />
          </div>
        )}
      </Panel>
    </div>
  );
}
