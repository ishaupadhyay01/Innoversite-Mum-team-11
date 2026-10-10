import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, GitCompareArrows } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button, EmptyState, ErrorState, PageHeader, Pagination, Select, SkeletonRows, Tag, inputClass } from "../components/ui";
import { useDebounce } from "../hooks/useDebounce";
import { api } from "../services/api";
import type { Alert } from "../types/api";
import { formatDate, formatDateTime } from "../utils/format";

const CHANGE_TYPES = ["New Document", "New Version", "Added Clause", "Removed Clause", "Modified Clause"];

export default function WhatsNewPage() {
  const [params] = useSearchParams();
  const focusId = params.get("alert") ? Number(params.get("alert")) : null;
  const [q, setQ] = useState("");
  const [changeType, setChangeType] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounce(q, 250);
  useEffect(() => setPage(1), [debounced, changeType]);

  const alerts = useQuery({
    queryKey: ["alerts", "timeline", debounced, changeType, page],
    queryFn: () => api.alerts({ q: debounced, change_type: changeType, page, page_size: 15 }),
    refetchInterval: 10_000,
  });

  return (
    <div>
      <PageHeader
        title="What's new"
        description="Regulatory updates in the order they were published to the repository. Change types and summaries come from a deterministic comparison of the old and new text."
      />
      <div className="mb-5 flex flex-wrap gap-3">
        <input className={clsx(inputClass, "max-w-xs")} placeholder="Search updates" aria-label="Search updates" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select
          label="Change type"
          className="w-auto"
          value={changeType}
          onChange={setChangeType}
          options={[{ value: "", label: "All change types" }, ...CHANGE_TYPES.map((c) => ({ value: c, label: c }))]}
        />
      </div>
      {alerts.isLoading && <SkeletonRows rows={5} />}
      {alerts.isError && <ErrorState error={alerts.error} onRetry={() => alerts.refetch()} />}
      {alerts.data && alerts.data.items.length === 0 && <EmptyState title="No updates match">Uploading a new document or a new version adds an update here.</EmptyState>}
      {alerts.data && alerts.data.items.length > 0 && (
        <ol className="relative space-y-4 border-l-2 border-line pl-6">
          {alerts.data.items.map((a) => (
            <UpdateCard key={a.id} alert={a} focused={a.id === focusId} />
          ))}
        </ol>
      )}
      {alerts.data && (
        <div className="mt-6">
          <Pagination page={page} totalPages={Math.ceil(alerts.data.total / alerts.data.page_size)} total={alerts.data.total} onChange={setPage} label="updates" />
        </div>
      )}
    </div>
  );
}

function UpdateCard({ alert, focused }: { alert: Alert; focused: boolean }) {
  const qc = useQueryClient();
  const ref = useRef<HTMLLIElement>(null);
  const mark = useMutation({
    mutationFn: (read: boolean) => api.markAlert(alert.id, read),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  useEffect(() => {
    if (focused) {
      ref.current?.scrollIntoView({ block: "center" });
      if (!alert.is_read) mark.mutate(true);
    }
  }, [focused]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <li ref={ref} className="relative">
      <span className={clsx("absolute -left-[33px] top-5 h-3.5 w-3.5 rounded-full border-2 border-canvas", alert.is_read ? "bg-faint" : "bg-version")} aria-hidden />
      <article className={clsx("rounded-lg bg-surface p-5 shadow-panel", focused && "ring-2 ring-version/50")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
              <span className="font-semibold text-ink">{alert.regulator}</span>
              <span>{formatDateTime(alert.event_time)}</span>
              {alert.source === "initial_import" && <Tag title="Recorded from the dataset metadata's original upload timestamp">Historical record</Tag>}
              {!alert.is_read && <Tag tone="version">Unread</Tag>}
            </div>
            <h2 className="mt-1 break-words text-[17px] font-semibold">{alert.document_name}</h2>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {alert.change_types.map((c) => (
              <Tag key={c} tone={c === "New Version" || c === "New Document" ? "version" : "neutral"}>
                {c}
              </Tag>
            ))}
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-faint">Previous version</dt>
            <dd>{alert.previous_version_label ?? "None"}</dd>
          </div>
          <div>
            <dt className="text-xs text-faint">New version</dt>
            <dd>{alert.new_version_label}</dd>
          </div>
          <div>
            <dt className="text-xs text-faint">Effective date</dt>
            <dd>{formatDate(alert.effective_date)}</dd>
          </div>
          <div>
            <dt className="text-xs text-faint">Uploaded</dt>
            <dd>{formatDate(alert.event_time)}</dd>
          </div>
        </dl>
        <p className="mt-3 text-[15px] leading-relaxed text-ink">{alert.summary}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {alert.previous_version_id && (
            <Link
              to={`/compare?base=${alert.previous_version_id}&target=${alert.version_id}`}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-version-soft px-3 text-sm font-medium text-version hover:bg-version-soft/70"
            >
              <GitCompareArrows className="h-4 w-4" /> Compare versions
            </Link>
          )}
          <Link to={`/viewer/${alert.version_id}`} className="inline-flex h-8 items-center rounded-md border border-line px-3 text-sm hover:bg-sunken">
            Open document
          </Link>
          <Button size="sm" variant="ghost" icon={<Check className="h-4 w-4" />} loading={mark.isPending} onClick={() => mark.mutate(!alert.is_read)}>
            {alert.is_read ? "Mark unread" : "Mark read"}
          </Button>
        </div>
      </article>
    </li>
  );
}
