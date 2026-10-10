import clsx from "clsx";
import type { ReactNode } from "react";

export function Card({ title, actions, children, className }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("rounded-lg border border-line bg-white", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "pass" | "fail" | "na" }) {
  return (
    <div className="rounded-lg border border-line bg-white px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-soft">{label}</div>
      <div
        className={clsx(
          "mt-1 font-mono text-2xl tabular-nums",
          tone === "pass" && "text-pass",
          tone === "fail" && "text-fail",
          tone === "na" && "text-na",
        )}
      >
        {value}
      </div>
    </div>
  );
}
