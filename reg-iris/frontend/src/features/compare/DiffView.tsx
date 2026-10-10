import clsx from "clsx";
import type { ChangeType, ClauseChange } from "@/api/types";
import { StatusBadge } from "@/components/ui/Badge";

const rowTone: Record<ChangeType, string> = {
  ADDED: "border-l-pass bg-pass-tint/40",
  REMOVED: "border-l-fail bg-fail-tint/40",
  MODIFIED: "border-l-warn bg-warn-tint/30",
  UNCHANGED: "border-l-line",
};

export function InlineDiff({ change }: { change: ClauseChange }) {
  return (
    <p className="text-sm leading-relaxed">
      {change.inline.map((op, i) => (
        <span
          key={i}
          className={clsx(
            op.op === "insert" && "rounded-sm bg-pass-tint text-pass",
            op.op === "delete" && "rounded-sm bg-fail-tint text-fail line-through",
          )}
        >
          {op.text}{" "}
        </span>
      ))}
    </p>
  );
}

export function DiffView({ changes, leftLabel, rightLabel }: { changes: ClauseChange[]; leftLabel?: string; rightLabel?: string }) {
  if (changes.length === 0) return <p className="text-sm text-ink-soft">No differences.</p>;
  return (
    <div className="space-y-2">
      {(leftLabel || rightLabel) && (
        <div className="text-xs text-ink-soft">
          <span className="text-fail">− {leftLabel}</span> &nbsp;→&nbsp; <span className="text-pass">+ {rightLabel}</span>
        </div>
      )}
      {changes.map((c) => (
        <div key={`${c.change}-${c.clause_ref}`} className={clsx("rounded-md border border-line border-l-4 bg-white p-3", rowTone[c.change])}>
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <StatusBadge status={c.change} />
            <span className="text-sm font-semibold">{c.clause_ref}</span>
            {c.title && <span className="text-sm text-ink-soft">{c.title}</span>}
            <span className="ml-auto font-mono text-xs text-ink-faint">
              {c.old_page != null && `p.${c.old_page}`}
              {c.old_page != null && c.new_page != null && " → "}
              {c.new_page != null && `p.${c.new_page}`}
              {c.change === "MODIFIED" && ` · ${(c.similarity * 100).toFixed(0)}% similar`}
            </span>
          </div>
          {c.change === "UNCHANGED" ? <p className="text-sm text-ink-soft">{c.new_text}</p> : <InlineDiff change={c} />}
        </div>
      ))}
    </div>
  );
}
