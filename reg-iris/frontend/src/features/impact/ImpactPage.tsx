import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import { rulesApi } from "@/api/rules";
import type { LintIssue, RuleSet, TradeDataset } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/Feedback";
import { FilePicker } from "@/components/ui/FilePicker";
import { fmtInt } from "@/lib/format";

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <Card title={<span className="flex items-center gap-2">{done ? <CheckCircle2 className="h-4 w-4 text-pass" /> : <span className="flex h-5 w-5 items-center justify-center rounded-full bg-canvas text-xs">{n}</span>}{title}</span>}>
      {children}
    </Card>
  );
}

function LintList({ issues }: { issues: LintIssue[] }) {
  const shown = issues.filter((i) => i.level !== "INFO");
  if (!shown.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {shown.map((i, k) => (
        <li key={k} className={`text-xs ${i.level === "ERROR" ? "text-fail" : "text-warn"}`}>
          <strong>{i.rule_code ?? "file"}</strong>: {i.message}
        </li>
      ))}
    </ul>
  );
}

/** Wizard: (1) regulatory document → (2) rules JSON → (3) trade CSV → run. Each file is validated on upload. */
export function ImpactPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [versionId, setVersionId] = useState("");
  const [rulesFile, setRulesFile] = useState<File | null>(null);
  const [tradesFile, setTradesFile] = useState<File | null>(null);
  const [selectedSets, setSelectedSets] = useState<string[]>([]);
  const [dataset, setDataset] = useState<TradeDataset | null>(null);

  const docs = useQuery({ queryKey: ["documents", "active"], queryFn: () => ingestionApi.listDocuments({ size: 200 }) });
  const ruleSets = useQuery({ queryKey: ["rule-sets"], queryFn: rulesApi.listRuleSets });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: rulesApi.listDatasets });

  const uploadRules = useMutation({
    mutationFn: () => rulesApi.uploadRules(rulesFile!),
    onSuccess: (r) => {
      setRulesFile(null);
      setSelectedSets((s) => Array.from(new Set([...s, r.rule_set.id])));
      void qc.invalidateQueries({ queryKey: ["rule-sets"] });
    },
  });
  const uploadTrades = useMutation({
    mutationFn: () => rulesApi.uploadDataset(tradesFile!),
    onSuccess: (r) => {
      setDataset(r.dataset);
      setTradesFile(null);
      void qc.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
  const run = useMutation({
    mutationFn: () => rulesApi.startRun(dataset!.id, selectedSets, versionId || undefined),
    onSuccess: (r) => navigate(`/impact/runs/${r.id}`),
  });

  const toggleSet = (rs: RuleSet) =>
    setSelectedSets((s) => (s.includes(rs.id) ? s.filter((x) => x !== rs.id) : [...s, rs.id]));

  return (
    <>
      <PageHeader title="Impact analysis" subtitle="Check a trade dataset against JSON rule sets and get an explained Impact Matrix" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Step n={1} title="Regulatory document" done={!!versionId}>
          <p className="mb-2 text-xs text-ink-soft">The regulation this analysis is traced to. Upload new ones under Documents.</p>
          <select className="input" value={versionId} onChange={(e) => setVersionId(e.target.value)}>
            <option value="">(optional) select…</option>
            {docs.data?.items.filter((d) => d.active_version).map((d) => (
              <option key={d.id} value={d.active_version!.id}>{d.regulator} — {d.title} ({d.active_version!.version_label})</option>
            ))}
          </select>
        </Step>

        <Step n={2} title="Rule sets (JSON)" done={selectedSets.length > 0}>
          <FilePicker accept=".json,application/json" label="Upload a rules JSON" file={rulesFile} onFile={setRulesFile} />
          {rulesFile && <Button className="mt-2 w-full" disabled={uploadRules.isPending} onClick={() => uploadRules.mutate()}>Validate & upload</Button>}
          <ErrorBanner error={uploadRules.error} />
          <ul className="mt-3 space-y-2">
            {ruleSets.data?.map((rs) => (
              <li key={rs.id} className="rounded-md border border-line p-2">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={selectedSets.includes(rs.id)} onChange={() => toggleSet(rs)} />
                  <Badge tone="brand">{rs.regulator}</Badge>
                  <span>{rs.rule_count} rules · v{rs.version_number}</span>
                </label>
                <LintList issues={rs.lint} />
              </li>
            ))}
          </ul>
          {!selectedSets.length && !!ruleSets.data?.length && <p className="mt-2 text-xs text-ink-soft">None selected = all active rule sets.</p>}
        </Step>

        <Step n={3} title="Trade dataset (CSV)" done={!!dataset && dataset.status !== "INVALID"}>
          <FilePicker accept=".csv,text/csv" label="Upload trades CSV" file={tradesFile} onFile={setTradesFile} />
          {tradesFile && <Button className="mt-2 w-full" disabled={uploadTrades.isPending} onClick={() => uploadTrades.mutate()}>Validate & upload</Button>}
          <ErrorBanner error={uploadTrades.error} />
          <select className="input mt-3" value={dataset?.id ?? ""} onChange={(e) => setDataset(datasets.data?.find((d) => d.id === e.target.value) ?? null)}>
            <option value="">or pick an uploaded dataset…</option>
            {datasets.data?.map((d) => <option key={d.id} value={d.id}>{d.filename} ({fmtInt(d.row_count)} rows)</option>)}
          </select>
          {dataset && (
            <div className="mt-3 rounded-md bg-canvas p-2 text-xs">
              <div className="flex items-center gap-2"><StatusBadge status={dataset.status} /> {fmtInt(dataset.row_count)} trades</div>
              {dataset.validation.errors.map((e) => <div key={e} className="mt-1 text-fail">{e}</div>)}
              {Object.entries(dataset.validation.issue_counts).map(([field, issues]) => (
                <div key={field} className="mt-1 text-ink-soft">
                  <span className="font-mono">{field}</span>: {Object.entries(issues).map(([k, n]) => `${n} ${k}`).join(", ")}
                </div>
              ))}
            </div>
          )}
        </Step>
      </div>
      <div className="mt-6 flex items-center justify-end gap-3">
        <ErrorBanner error={run.error} />
        <Button disabled={!dataset || dataset.status === "INVALID" || !ruleSets.data?.length || run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Starting…" : "Run impact analysis"}
        </Button>
      </div>
    </>
  );
}
