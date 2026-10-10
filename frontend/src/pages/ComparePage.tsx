import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRightLeft } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, Field, Notice, PageHeader, Panel, Select, SkeletonRows, Stat, Tag } from "../components/ui";
import { api } from "../services/api";
import type { DiffClause, DiffRow, Version } from "../types/api";
import { formatDate } from "../utils/format";

export default function ComparePage() {
  const [params, setParams] = useSearchParams();
  const base = params.get("base") ? Number(params.get("base")) : null;
  const target = params.get("target") ? Number(params.get("target")) : null;
  const [showUnchanged, setShowUnchanged] = useState(false);

  const docs = useQuery({ queryKey: ["documents", "all-for-compare"], queryFn: () => api.documents({ page_size: 100 }) });
  const baseDetail = useQuery({ queryKey: ["version", base], queryFn: () => api.version(base!), enabled: base !== null });
  const docId = baseDetail.data?.version.document_id ?? null;
  const familyVersions = useQuery({ queryKey: ["versions", docId], queryFn: () => api.versions(docId!), enabled: docId !== null });

  const allVersions: { family: string; v: Version }[] = useMemo(
    () => (docs.data?.items ?? []).flatMap((d) => (d.latest_version ? [{ family: d.title, v: d.latest_version }] : [])),
    [docs.data],
  );
  const multiVersionDocs = (docs.data?.items ?? []).filter((d) => d.version_count > 1);

  const diff = useQuery({
    queryKey: ["compare", base, target],
    queryFn: () => api.compare(base!, target!),
    enabled: base !== null && target !== null && base !== target,
  });

  const rows = (diff.data?.rows ?? []).filter((r) => showUnchanged || r.change !== "unchanged");

  return (
    <div>
      <PageHeader
        title="Version comparison"
        description="Side-by-side comparison of two versions. Clauses are aligned with Python difflib; a clause is marked modified when it is textually similar but not identical. The comparison does not judge legal significance."
      />

      <Panel className="mb-6">
        <div className="grid items-end gap-4 md:grid-cols-[1fr_auto_1fr]">
          <Field label="Previous version">
            <Select
              label="Previous version"
              value={base ? String(base) : ""}
              onChange={(v) => setParams(v ? { base: v, ...(target ? { target: String(target) } : {}) } : {})}
              options={[
                { value: "", label: "Choose a version…" },
                ...(familyVersions.data ?? []).map((v) => ({ value: String(v.id), label: `${v.file_name} (${v.version_label})` })),
                ...(!familyVersions.data ? allVersions.map(({ family, v }) => ({ value: String(v.id), label: `${family}: ${v.version_label}` })) : []),
              ]}
            />
          </Field>
          <ArrowRightLeft className="mb-2 hidden h-5 w-5 text-faint md:block" aria-hidden />
          <Field label="Current version">
            <Select
              label="Current version"
              value={target ? String(target) : ""}
              onChange={(v) => setParams({ ...(base ? { base: String(base) } : {}), ...(v ? { target: v } : {}) })}
              options={[
                { value: "", label: base ? "Choose a version…" : "Choose the previous version first" },
                ...(familyVersions.data ?? []).filter((v) => v.id !== base).map((v) => ({ value: String(v.id), label: `${v.file_name} (${v.version_label})` })),
              ]}
            />
          </Field>
        </div>
        {!base && multiVersionDocs.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">Documents with several versions:</span>
            {multiVersionDocs.map((d) => (
              <QuickCompare key={d.id} documentId={d.id} title={d.title} />
            ))}
          </div>
        )}
      </Panel>

      {base === null || target === null ? (
        <EmptyState title="Choose two versions to compare">Pick a document version on the left, then the version to compare it with.</EmptyState>
      ) : base === target ? (
        <Notice tone="warn">Choose two different versions.</Notice>
      ) : diff.isLoading ? (
        <SkeletonRows rows={6} />
      ) : diff.isError ? (
        <ErrorState error={diff.error} onRetry={() => diff.refetch()} />
      ) : diff.data ? (
        <>
          {!diff.data.same_document && (
            <div className="mb-4">
              <Notice tone="warn">These versions belong to different documents; the comparison is purely textual.</Notice>
            </div>
          )}
          <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Added clauses" value={diff.data.stats.added ?? 0} tone={diff.data.stats.added ? "pass" : undefined} />
            <Stat label="Removed clauses" value={diff.data.stats.removed ?? 0} tone={diff.data.stats.removed ? "fail" : undefined} />
            <Stat label="Modified clauses" value={diff.data.stats.modified ?? 0} tone={diff.data.stats.modified ? "version" : undefined} />
            <Stat label="Unchanged clauses" value={diff.data.stats.unchanged ?? 0} />
          </div>
          <Panel className="mb-5" title="Change summary">
            <div className="grid gap-4 text-sm md:grid-cols-2">
              <VersionMeta v={diff.data.base} label="Previous" />
              <VersionMeta v={diff.data.target} label="Current" />
            </div>
            <p className="mt-4 text-[15px] leading-relaxed">{diff.data.summary}</p>
            <p className="mt-2 text-xs text-faint">Method: {diff.data.method}</p>
          </Panel>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Clause by clause</h2>
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={showUnchanged} onChange={(e) => setShowUnchanged(e.target.checked)} /> Show unchanged clauses
            </label>
          </div>
          {rows.length === 0 ? (
            <EmptyState title="No textual differences">Both versions contain the same clauses.</EmptyState>
          ) : (
            <div className="space-y-3">
              {rows.map((r, i) => (
                <DiffRowView key={i} row={r} baseId={diff.data!.base.id} targetId={diff.data!.target.id} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function QuickCompare({ documentId, title }: { documentId: number; title: string }) {
  const versions = useQuery({ queryKey: ["versions", documentId], queryFn: () => api.versions(documentId) });
  const v = versions.data;
  if (!v || v.length < 2) return null;
  return (
    <Link to={`/compare?base=${v[v.length - 2].id}&target=${v[v.length - 1].id}`} className="rounded-md bg-version-soft px-2.5 py-1 font-medium text-version hover:bg-version-soft/70">
      {title}: {v[v.length - 2].version_label} to {v[v.length - 1].version_label}
    </Link>
  );
}

function VersionMeta({ v, label }: { v: Version; label: string }) {
  return (
    <div className="rounded-md bg-sunken px-4 py-3">
      <div className="text-xs text-faint">{label}</div>
      <div className="font-medium">{v.file_name}</div>
      <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
        <Tag tone="version">{v.version_label}</Tag>
        <span>Effective {formatDate(v.effective_date)}</span>
        <span>{v.paragraph_count} clauses</span>
      </div>
    </div>
  );
}

const CHANGE_STYLE: Record<DiffRow["change"], { label: string; cls: string }> = {
  added: { label: "Added", cls: "bg-pass-soft text-pass" },
  removed: { label: "Removed", cls: "bg-fail-soft text-fail" },
  modified: { label: "Modified", cls: "bg-version-soft text-version" },
  unchanged: { label: "Unchanged", cls: "bg-sunken text-muted" },
};

function DiffRowView({ row, baseId, targetId }: { row: DiffRow; baseId: number; targetId: number }) {
  const style = CHANGE_STYLE[row.change];
  return (
    <div className="overflow-hidden rounded-lg bg-surface shadow-panel">
      <div className="flex items-center gap-3 border-b border-line px-4 py-2">
        <span className={clsx("rounded px-2 py-0.5 text-xs font-medium", style.cls)}>{style.label}</span>
        {row.change === "modified" && row.similarity !== null && <span className="text-xs text-faint">{Math.round(row.similarity * 100)}% similar</span>}
      </div>
      <div className="grid md:grid-cols-2 md:divide-x md:divide-line">
        <ClauseCell clause={row.old} side="old" row={row} versionId={baseId} />
        <ClauseCell clause={row.new} side="new" row={row} versionId={targetId} />
      </div>
    </div>
  );
}

function ClauseCell({ clause, side, row, versionId }: { clause: DiffClause | null; side: "old" | "new"; row: DiffRow; versionId: number }) {
  if (!clause) {
    return <div className="hidden bg-sunken/50 px-5 py-4 text-sm italic text-faint md:block">{side === "old" ? "Not present in the previous version" : "Not present in the current version"}</div>;
  }
  const tint = row.change === "added" && side === "new" ? "bg-pass-soft/40" : row.change === "removed" && side === "old" ? "bg-fail-soft/40" : "";
  return (
    <div className={clsx("px-5 py-4", tint)}>
      <div className="mb-1.5 flex items-center justify-between text-xs text-faint">
        <span>{side === "old" ? "Previous" : "Current"}</span>
        <Link to={`/viewer/${versionId}?paragraph=v${versionId}-p${String(clause.ordinal).padStart(4, "0")}`} className="hover:text-accent hover:underline">
          {clause.location}
        </Link>
      </div>
      {row.change === "modified" && row.inline ? (
        <p className="reg-text whitespace-pre-line">
          {row.inline.map((seg, i) => {
            if (seg.op === "equal") return <span key={i}>{seg.text}</span>;
            if (seg.op === "delete" && side === "old") return <del key={i} className="bg-fail-soft text-fail decoration-fail/60">{seg.text}</del>;
            if (seg.op === "insert" && side === "new") return <ins key={i} className="bg-pass-soft text-pass no-underline">{seg.text}</ins>;
            return null;
          })}
        </p>
      ) : (
        <>
          {clause.heading && <p className="font-serif font-semibold">{clause.heading}</p>}
          <p className="reg-text whitespace-pre-line">{clause.body}</p>
        </>
      )}
    </div>
  );
}
