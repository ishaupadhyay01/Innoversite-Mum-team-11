import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Download, ExternalLink } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ErrorState, Kv, Panel, SkeletonRows, Tag } from "../components/ui";
import { api } from "../services/api";
import type { Paragraph } from "../types/api";
import { formatDate, formatDateTime } from "../utils/format";

export default function SourceViewerPage() {
  const { versionId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const id = Number(versionId);
  const paragraphId = params.get("paragraph");

  const detail = useQuery({ queryKey: ["version", id], queryFn: () => api.version(id), enabled: Number.isFinite(id) });
  const indexed = useQuery({
    queryKey: ["paragraph", paragraphId],
    queryFn: () => api.paragraph(paragraphId!, 0),
    enabled: !!paragraphId,
    retry: false,
  });

  const selected: Paragraph | undefined = useMemo(
    () => detail.data?.paragraphs.find((p) => p.paragraph_id === paragraphId) ?? detail.data?.paragraphs[0],
    [detail.data, paragraphId],
  );

  if (detail.isLoading) return <SkeletonRows rows={6} />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  if (!detail.data) return null;

  const { version, document } = detail.data;
  let frameSrc = version.source_url;
  if (version.source_type === "pdf" && selected?.page_start) frameSrc += `#page=${selected.page_start}`;
  if (version.source_type === "html" && selected?.anchor) frameSrc += `#${selected.anchor}`;

  return (
    <div>
      <button onClick={() => navigate(-1)} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-semibold tracking-[-0.01em]">{version.file_name}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span>{document.regulator}</span>
            <Tag tone="version">{version.version_label}</Tag>
            {!version.is_latest && <Tag tone="warn">Superseded version</Tag>}
            <span>Effective {formatDate(version.effective_date)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <a href={frameSrc} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm hover:bg-sunken">
            <ExternalLink className="h-4 w-4" /> Open in new tab
          </a>
          <a href={`${version.source_url}&download=true`} className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm hover:bg-sunken">
            <Download className="h-4 w-4" /> Download
          </a>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <div className="overflow-hidden rounded-lg bg-surface shadow-panel">
          <iframe
            key={frameSrc}
            title={`Source document ${version.file_name}`}
            src={frameSrc}
            className="h-[78vh] w-full bg-white"
            {...(version.source_type === "pdf" ? {} : { sandbox: "" })}
          />
        </div>

        <div className="space-y-5">
          <Panel title="Cited paragraph">
            {selected ? (
              <>
                <Kv
                  items={[
                    { label: "Location", value: selected.location },
                    { label: "Section", value: selected.heading ?? "—" },
                    { label: "Paragraph id", value: <code className="font-mono text-xs">{selected.paragraph_id}</code> },
                  ]}
                />
                <div className="mt-4 border-l-2 border-accent pl-4">
                  {selected.heading && <p className="mb-1 font-serif font-semibold">{selected.heading}</p>}
                  <p className="reg-text whitespace-pre-line">{selected.body}</p>
                </div>
                {paragraphId && indexed.isError && (
                  <p className="mt-3 text-xs text-warn">This paragraph is not currently in the search index.</p>
                )}
                {version.source_type !== "pdf" && (
                  <p className="mt-3 text-xs text-faint">
                    {version.source_type === "html" ? "HTML documents have no pages; the viewer jumps to the section anchor." : `Plain-text document: cited by line numbers, PDF pagination does not apply.`}
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">No paragraph selected.</p>
            )}
          </Panel>

          <Panel title="Clauses in this version" padded={false} description={`${detail.data.paragraphs.length} extracted with ${version.extractor ?? "parser"}`}>
            <ol className="scroll-thin max-h-[42vh] divide-y divide-line overflow-y-auto">
              {detail.data.paragraphs.map((p) => (
                <li key={p.paragraph_id}>
                  <button
                    onClick={() => setParams({ paragraph: p.paragraph_id })}
                    className={clsx(
                      "flex w-full items-start gap-3 px-5 py-2.5 text-left text-sm hover:bg-sunken",
                      selected?.paragraph_id === p.paragraph_id && "bg-accent-soft",
                    )}
                  >
                    <span className="w-16 flex-none text-xs text-faint">{p.location}</span>
                    <span className="min-w-0 flex-1 truncate text-ink">{p.heading ?? p.body.slice(0, 80)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel title="Version record">
            <Kv
              items={[
                { label: "Document", value: <Link className="text-accent hover:underline" to={`/documents?open=${document.id}`}>{document.title}</Link> },
                { label: "Uploaded", value: formatDateTime(version.uploaded_at) },
                { label: "Origin", value: version.origin === "seed" ? "Supplied dataset" : "User upload" },
                { label: "SHA-256", value: <code className="break-all font-mono text-xs">{version.content_hash}</code> },
              ]}
            />
          </Panel>
        </div>
      </div>
    </div>
  );
}
