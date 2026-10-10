import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import { fmtDateTime } from "@/lib/format";

/** Alert Panel: polls for new What's New alerts every 10s and pops a toast for each new one. */
export function AlertBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const seen = useRef<Set<string> | null>(null);
  const { data } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => ingestionApi.alerts(false),
    refetchInterval: 10_000,
  });
  const alerts = data ?? [];
  const unread = alerts.filter((a) => !a.read_at);

  useEffect(() => {
    if (!data) return; // only diff against real data, never the initial empty state
    const ids = new Set(data.map((a) => a.id));
    const alerts = data;
    if (seen.current) {
      const fresh = alerts.find((a) => !seen.current!.has(a.id));
      if (fresh) {
        setToast(fresh.message);
        void qc.invalidateQueries({ queryKey: ["whats-new"] });
        setTimeout(() => setToast(null), 6000);
      }
    }
    seen.current = ids;
  }, [data, qc]);

  const readAll = useMutation({
    mutationFn: ingestionApi.markAllAlertsRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="relative">
      <button
        aria-label={`Alerts (${unread.length} unread)`}
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-ink-soft hover:bg-canvas hover:text-ink"
      >
        <Bell className="h-5 w-5" />
        {unread.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-fail px-1 text-center text-[11px] font-semibold leading-[18px] text-white">
            {unread.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-96 rounded-lg border border-line bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <span className="text-sm font-semibold">Alerts</span>
            <button className="text-xs text-brand hover:underline" onClick={() => readAll.mutate()}>
              Mark all read
            </button>
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {alerts.length === 0 && <li className="px-4 py-6 text-center text-sm text-ink-soft">No alerts yet</li>}
            {alerts.map((a) => (
              <li key={a.id} className="border-b border-line last:border-0">
                <Link
                  to={a.card_id ? `/?card=${a.card_id}` : "/"}
                  onClick={() => {
                    setOpen(false);
                    if (!a.read_at) void ingestionApi.markAlertRead(a.id).then(() => qc.invalidateQueries({ queryKey: ["alerts"] }));
                  }}
                  className="block px-4 py-3 hover:bg-canvas"
                >
                  <div className={`text-sm ${a.read_at ? "text-ink-soft" : "font-medium"}`}>{a.message}</div>
                  <div className="mt-0.5 text-xs text-ink-faint">{fmtDateTime(a.created_at)}</div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {toast &&
        createPortal(
          <div role="status" className="fixed bottom-6 right-6 z-50 max-w-sm rounded-lg bg-ink px-4 py-3 text-sm text-white shadow-xl">
            <div className="text-xs font-semibold uppercase tracking-wide text-white/60">What's new</div>
            {toast}
          </div>,
          document.body,
        )}
    </div>
  );
}
