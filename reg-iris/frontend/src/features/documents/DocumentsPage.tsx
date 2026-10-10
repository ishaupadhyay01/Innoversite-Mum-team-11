import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useDebounce } from "@/lib/useDebounce";
import { UploadDocumentDialog } from "./UploadDocumentDialog";

export function DocumentsPage() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [uploading, setUploading] = useState(false);
  const dq = useDebounce(q);
  const docs = useQuery({
    queryKey: ["documents", page, dq],
    queryFn: () => ingestionApi.listDocuments({ page, size: 20, q: dq || undefined }),
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.active_version?.processing_status !== "READY") ? 3000 : false,
  });

  return (
    <>
      <PageHeader title="Regulatory documents" subtitle="Repository with full version history"
        actions={<Button onClick={() => setUploading(true)}><Plus className="h-4 w-4" /> Upload</Button>} />
      <input className="input mb-4 max-w-sm" placeholder="Filter by title…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <ErrorBanner error={docs.error} />
      {docs.isLoading && <Spinner />}
      {docs.data?.total === 0 && <EmptyState title="No documents yet">Upload a regulation to get started.</EmptyState>}
      {docs.data && docs.data.total > 0 && (
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Title</th><th className="th">Regulator</th><th className="th">Jurisdiction</th>
                <th className="th">Active version</th><th className="th">Effective</th><th className="th">Versions</th><th className="th">Updated</th>
              </tr>
            </thead>
            <tbody>
              {docs.data.items.map((d) => (
                <tr key={d.id} className="hover:bg-canvas">
                  <td className="td"><Link to={`/documents/${d.id}`} className="font-medium text-brand hover:underline">{d.title}</Link></td>
                  <td className="td"><Badge tone="brand">{d.regulator}</Badge></td>
                  <td className="td">{d.jurisdiction ?? "—"}</td>
                  <td className="td">
                    {d.active_version ? <span className="font-mono text-xs">{d.active_version.version_label}</span> : <StatusBadge status="INACTIVE" />}
                  </td>
                  <td className="td">{fmtDate(d.active_version?.effective_date)}</td>
                  <td className="td tabular-nums">{d.version_count}</td>
                  <td className="td text-ink-soft">{fmtDateTime(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3"><Pagination page={page} pages={docs.data.pages} total={docs.data.total} onPage={setPage} /></div>
        </div>
      )}
      {uploading && <UploadDocumentDialog onClose={() => setUploading(false)} />}
    </>
  );
}
