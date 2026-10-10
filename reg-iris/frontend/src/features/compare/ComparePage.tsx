import { useMutation, useQuery, useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { ingestionApi } from "@/api/ingestion";
import { searchApi } from "@/api/search";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { DiffView } from "./DiffView";

/** Pick any two versions — of the same regulation or of different regulations — and diff them clause by clause. */
export function ComparePage() {
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [showUnchanged, setShowUnchanged] = useState(false);
  const docs = useQuery({ queryKey: ["documents", "all"], queryFn: () => ingestionApi.listDocuments({ size: 200 }) });
  const details = useQueries({
    queries: (docs.data?.items ?? []).map((d) => ({ queryKey: ["document", d.id], queryFn: () => ingestionApi.getDocument(d.id) })),
  });
  const options = details.flatMap((q) =>
    (q.data?.versions ?? []).map((v) => ({ id: v.id, label: `${q.data!.regulator} — ${q.data!.title} (${v.version_label}${v.status === "ACTIVE" ? ", active" : ""})` })),
  );
  const compare = useMutation({ mutationFn: () => searchApi.compare(left, right, showUnchanged) });
  const s = compare.data?.summary;

  return (
    <>
      <PageHeader title="Compare" subtitle="Highlight added, removed and modified clauses between two versions or regulations" />
      <Card>
        <div className="grid items-end gap-3 md:grid-cols-[1fr_1fr_auto]">
          {[["Base (left)", left, setLeft], ["Compare with (right)", right, setRight]].map(([label, value, set]) => (
            <div key={label as string}>
              <label className="label">{label as string}</label>
              <select className="input" value={value as string} onChange={(e) => (set as (v: string) => void)(e.target.value)}>
                <option value="">Select a version…</option>
                {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </div>
          ))}
          <Button disabled={!left || !right || left === right || compare.isPending} onClick={() => compare.mutate()}>
            {compare.isPending ? "Comparing…" : "Compare"}
          </Button>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" checked={showUnchanged} onChange={(e) => setShowUnchanged(e.target.checked)} /> Include unchanged clauses
        </label>
      </Card>
      <div className="mt-6">
        {docs.isLoading && <Spinner />}
        <ErrorBanner error={compare.error} />
        {compare.data && s && (
          <>
            <div className="mb-3 flex gap-4 font-mono text-sm">
              <span className="text-pass">+{s.ADDED} added</span>
              <span className="text-warn">~{s.MODIFIED} modified</span>
              <span className="text-fail">−{s.REMOVED} removed</span>
              <span className="text-na">{s.UNCHANGED} unchanged</span>
            </div>
            <DiffView changes={compare.data.changes} leftLabel={compare.data.left_label} rightLabel={compare.data.right_label} />
          </>
        )}
      </div>
    </>
  );
}
