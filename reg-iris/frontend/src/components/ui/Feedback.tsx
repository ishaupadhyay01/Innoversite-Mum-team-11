import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/api/client";

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-ink-soft">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <div role="alert" className="flex gap-2 rounded-md border border-fail/30 bg-fail-tint px-3 py-2 text-sm text-fail">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <div className="font-medium">{e ? e.message : String((error as Error)?.message ?? error)}</div>
        {e && (
          <div className="font-mono text-xs opacity-80">
            {e.code}
            {e.requestId ? ` · request ${e.requestId}` : ""}
          </div>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-white px-6 py-10 text-center">
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="mt-1 text-sm text-ink-soft">{children}</div>}
    </div>
  );
}
