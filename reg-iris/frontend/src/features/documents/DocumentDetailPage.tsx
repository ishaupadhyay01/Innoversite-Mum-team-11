import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Upload } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import type { DocumentVersion } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { DiffView } from "@/features/compare/DiffView";
import { fmtBytes, fmtDate, fmtDateTime } from "@/lib/format";
import { UploadDocumentDialog } from "./UploadDocumentDialog";

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const doc = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => ingestionApi.getDocument(documentId),
    refetchInterval: (q) => (q.state.data?.versions.some((v) => v.processing_status !== "READY" && v.processing_status !== "FAILED") ? 2000 : false),
  });
  const versions = [...(doc.data?.versions ?? [])].reverse();
  const selected: DocumentVersion | undefined =
    versions.find((v) => v.id === params.get("version")) ?? versions.find((v) => v.status === "ACTIVE") ?? versions[0];
  const diffFor = params.get("diff");

  const clauses = useQuery({
    queryKey: ["clauses", selected?.id],
    queryFn: () => ingestionApi.clauses(selected!.id),
    enabled: !!selected && selected.processing_status === "READY" && !diffFor,
  });
  const diff = useQuery({ queryKey: ["diff", diffFor], queryFn: () => ingestionApi.diff(diffFor!), enabled: !!diffFor });
  const activate = useMutation({
    mutationFn: ingestionApi.activate,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["document", documentId] }),
  });

  if (doc.isLoading) return <Spinner />;
  if (doc.error) return <ErrorBanner error={doc.error} />;
  const d = doc.data!;

  return (
    <>
      <PageHeader
        title={d.title}
        subtitle={[d.regulator, d.jurisdiction, d.category].filter(Boolean).join(" · ")}
        actions={<Button onClick={() => setUploading(true)}><Upload className="h-4 w-4" /> New version</Button>}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Version history" className="lg:col-span-1">
          <ol className="space-y-2">
            {versions.map((v, i) => (
              <li key={v.id} className={`rounded-md border p-3 ${v.id === selected?.id && !diffFor ? "border-brand bg-brand-tint/40" : "border-line"}`}>
                <div className="flex items-center gap-2">
                  <button className="font-mono text-sm font-semibold hover:underline" onClick={() => setParams({ version: v.id })}>{v.version_label}</button>
                  <StatusBadge status={v.status} />
                  {v.processing_status !== "READY" && <StatusBadge status={v.processing_status} />}
                </div>
                <div className="mt-1 text-xs text-ink-soft">
                  {v.original_filename} · {fmtBytes(v.file_size)} · effective {fmtDate(v.effective_date)}
                </div>
                <div className="text-xs text-ink-faint">uploaded {fmtDateTime(v.uploaded_at)}</div>
                {v.quality_warnings?.map((w) => <div key={w} className="mt-1 text-xs text-warn">⚠ {w}</div>)}
                {v.error_message && <div className="mt-1 text-xs text-fail">{v.error_message}</div>}
                <div className="mt-2 flex flex-wrap gap-2">
                  {v.file_url && <a className="inline-flex items-center gap-1 text-xs text-brand hover:underline" href={v.file_url} target="_blank" rel="noreferrer">Open file <ExternalLink className="h-3 w-3" /></a>}
                  {i < versions.length - 1 && v.processing_status === "READY" && (
                    <button className="text-xs text-brand hover:underline" onClick={() => setParams({ diff: v.id })}>Diff vs previous</button>
                  )}
                  {v.status !== "ACTIVE" && v.processing_status === "READY" && (
                    <button className="text-xs text-brand hover:underline" disabled={activate.isPending} onClick={() => activate.mutate(v.id)}>Make active</button>
                  )}
                </div>
              </li>
            ))}
          </ol>
          <ErrorBanner error={activate.error} />
        </Card>

        <div className="lg:col-span-2">
          {diffFor ? (
            <Card title="Changes vs previous version" actions={<button className="text-xs text-brand hover:underline" onClick={() => setParams({})}>Close diff</button>}>
              {diff.isLoading && <Spinner />}
              <ErrorBanner error={diff.error} />
              {diff.data && (
                <>
                  <p className="mb-3 text-sm">{diff.data.headline}</p>
                  <DiffView changes={diff.data.changes} />
                </>
              )}
            </Card>
          ) : (
            <Card title={selected ? `Clauses — ${selected.version_label}` : "Clauses"}>
              {clauses.isLoading && <Spinner />}
              <div className="space-y-3">
                {clauses.data?.map((c) => (
                  <div key={c.id} id={c.anchor ?? undefined} className="border-b border-line pb-3 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{c.clause_ref}</span>
                      {c.title && <span className="text-sm text-ink-soft">{c.title}</span>}
                      <a className="ml-auto" href={`${selected?.file_url}${c.anchor ? `#${c.anchor}` : `#page=${c.page_start}`}`} target="_blank" rel="noreferrer">
                        <Badge>p.{c.page_start}</Badge>
                      </a>
                    </div>
                    <p className="mt-1 text-sm leading-relaxed">{c.text}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
      {uploading && <UploadDocumentDialog fixedDocumentId={d.id} onClose={() => setUploading(false)} />}
    </>
  );
}
