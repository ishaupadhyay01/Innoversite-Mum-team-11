import clsx from "clsx";
import type { ReactNode } from "react";

type Tone = "pass" | "fail" | "na" | "warn" | "brand" | "neutral";

const tones: Record<Tone, string> = {
  pass: "bg-pass-tint text-pass",
  fail: "bg-fail-tint text-fail",
  na: "bg-na-tint text-na",
  warn: "bg-warn-tint text-warn",
  brand: "bg-brand-tint text-brand",
  neutral: "bg-canvas text-ink-soft",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

const statusTone: Record<string, Tone> = {
  PASS: "pass", FAIL: "fail", NOT_APPLICABLE: "na", ERROR: "warn",
  ACTIVE: "pass", INACTIVE: "na", READY: "pass", FAILED: "fail", PROCESSING: "brand", UPLOADED: "brand",
  COMPLETED: "pass", RUNNING: "brand", QUEUED: "neutral",
  ADDED: "pass", REMOVED: "fail", MODIFIED: "warn", UNCHANGED: "na",
  VALID: "pass", VALID_WITH_WARNINGS: "warn", INVALID: "fail",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone[status] ?? "neutral"}>{status === "NOT_APPLICABLE" ? "N/A" : status.replace(/_/g, " ")}</Badge>;
}
