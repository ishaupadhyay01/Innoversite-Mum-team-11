import clsx from "clsx";
import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { Segment } from "../../types/api";
import { statusLabel } from "../../utils/format";

// ----------------------------------------------------------------------------- buttons

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-55",
        size === "sm" && "h-8 px-3 text-sm",
        size === "md" && "h-9 px-4 text-sm",
        size === "lg" && "h-11 px-5 text-[15px]",
        variant === "primary" && "bg-accent text-white hover:bg-accent/90",
        variant === "secondary" && "border border-line bg-surface text-ink hover:bg-sunken",
        variant === "ghost" && "text-muted hover:bg-sunken hover:text-ink",
        variant === "danger" && "bg-fail text-white hover:bg-fail/90",
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

// ----------------------------------------------------------------------------- badges

const STATUS_STYLES: Record<string, string> = {
  PASS: "bg-pass-soft text-pass",
  COMPLIANT: "bg-pass-soft text-pass",
  indexed: "bg-pass-soft text-pass",
  completed: "bg-pass-soft text-pass",
  ok: "bg-pass-soft text-pass",
  FAIL: "bg-fail-soft text-fail",
  NON_COMPLIANT: "bg-fail-soft text-fail",
  failed: "bg-fail-soft text-fail",
  unreachable: "bg-fail-soft text-fail",
  NOT_APPLICABLE: "bg-na-soft text-na",
  queued: "bg-na-soft text-na",
  ERROR: "bg-warn-soft text-warn",
  degraded: "bg-warn-soft text-warn",
  completed_with_errors: "bg-warn-soft text-warn",
  processing: "bg-accent-soft text-accent",
  running: "bg-accent-soft text-accent",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium",
        STATUS_STYLES[status] ?? "bg-sunken text-muted",
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {label ?? statusLabel(status)}
    </span>
  );
}

export function Tag({ children, tone = "neutral", title }: { children: ReactNode; tone?: "neutral" | "version" | "accent" | "warn"; title?: string }) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-sunken text-muted",
        tone === "version" && "bg-version-soft text-version",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "warn" && "bg-warn-soft text-warn",
      )}
    >
      {children}
    </span>
  );
}

// ----------------------------------------------------------------------------- layout blocks

export function Panel({ id, title, actions, children, className, padded = true, description }: {
  id?: string;
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  description?: ReactNode;
}) {
  return (
    <section id={id} className={clsx("rounded-lg bg-surface shadow-panel", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx(padded && "p-5")}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.01em] text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-[68ch] text-[15px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "fail" | "pass" | "version" }) {
  return (
    <div className="rounded-lg bg-surface px-5 py-4 shadow-panel">
      <div className="text-sm text-muted">{label}</div>
      <div
        className={clsx(
          "mt-1 text-[28px] font-semibold leading-none tracking-[-0.02em]",
          tone === "fail" && "text-fail",
          tone === "pass" && "text-pass",
          tone === "version" && "text-version",
          !tone && "text-ink",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-faint">{hint}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, children, action, icon }: { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-3 text-faint">{icon ?? <Inbox className="h-8 w-8" aria-hidden />}</div>
      <h3 className="font-semibold text-ink">{title}</h3>
      {children && <div className="mt-1.5 max-w-[52ch] text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-fail/30 bg-fail-soft px-4 py-3 text-sm text-fail">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">Request failed</p>
        <p className="mt-0.5 text-fail/90">{message}</p>
      </div>
      {onRetry && (
        <button className="font-medium underline underline-offset-2" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return (
    <div
      className={clsx(
        "rounded-md px-3.5 py-2.5 text-sm",
        tone === "info" && "bg-accent-soft text-ink",
        tone === "warn" && "bg-warn-soft text-ink",
      )}
    >
      {children}
    </div>
  );
}

// ----------------------------------------------------------------------------- pagination

export function Pagination({ page, totalPages, onChange, total, label = "results" }: {
  page: number;
  totalPages: number;
  total?: number;
  onChange: (page: number) => void;
  label?: string;
}) {
  if (totalPages <= 1) {
    return total !== undefined ? <p className="text-sm text-muted">{total.toLocaleString("en-GB")} {label}</p> : null;
  }
  return (
    <nav className="flex items-center justify-between gap-3 text-sm" aria-label="Pagination">
      <span className="text-muted">
        Page {page} of {totalPages}
        {total !== undefined && `, ${total.toLocaleString("en-GB")} ${label}`}
      </span>
      <div className="flex gap-1.5">
        <Button size="sm" onClick={() => onChange(page - 1)} disabled={page <= 1} icon={<ChevronLeft className="h-4 w-4" />} aria-label="Previous page">
          Previous
        </Button>
        <Button size="sm" onClick={() => onChange(page + 1)} disabled={page >= totalPages} aria-label="Next page">
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

// ----------------------------------------------------------------------------- form controls

export function Field({ label, children, hint, htmlFor }: { label: string; children: ReactNode; hint?: ReactNode; htmlFor?: string }) {
  return (
    <label className="block" htmlFor={htmlFor}>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "h-9 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

export function Select({ value, onChange, options, label, className }: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  label: string;
  className?: string;
}) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={clsx(inputClass, "pr-8", className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function CheckList({ options, selected, onToggle, empty }: {
  options: { value: string; label?: string; count?: number }[];
  selected: string[];
  onToggle: (value: string) => void;
  empty?: string;
}) {
  if (!options.length) return <p className="text-sm text-faint">{empty ?? "No values"}</p>;
  return (
    <ul className="space-y-1">
      {options.map((o) => {
        const checked = selected.includes(o.value);
        return (
          <li key={o.value}>
            <label className="flex cursor-pointer items-center gap-2.5 rounded px-1.5 py-1 text-sm hover:bg-sunken">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-line accent-[rgb(var(--accent))]"
                checked={checked}
                onChange={() => onToggle(o.value)}
              />
              <span className="flex-1 text-ink">{o.label ?? o.value}</span>
              {o.count !== undefined && <span className="text-xs tabular-nums text-faint">{o.count}</span>}
            </label>
          </li>
        );
      })}
    </ul>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-sunken p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded px-3 py-1 text-sm font-medium transition-colors",
            value === o.value ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ----------------------------------------------------------------------------- drawer

export function Drawer({ open, onClose, title, children, width = "max-w-2xl" }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-navy/40" aria-label="Close panel" onClick={onClose} />
      <div className={clsx("relative flex h-full w-full flex-col bg-surface shadow-pop", width)}>
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0 text-[17px] font-semibold text-ink">{title}</div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-sunken hover:text-ink" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- text

/** Renders highlight segments as text nodes — never as HTML. */
export function SegmentText({ segments, fallback }: { segments: Segment[]; fallback?: string }) {
  if (!segments.length) return <>{fallback ?? ""}</>;
  return (
    <>
      {segments.map((s, i) =>
        s.highlight ? (
          <mark key={i} className="hl">
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}

export function Kv({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-2 text-sm">
      {items.map((i) => (
        <div key={i.label} className="contents">
          <dt className="text-muted">{i.label}</dt>
          <dd className="min-w-0 break-words text-ink">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[12.5px] text-ink">{children}</code>;
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="scroll-thin overflow-x-auto rounded-md bg-sunken p-3 font-mono text-[12.5px] leading-relaxed text-ink">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
