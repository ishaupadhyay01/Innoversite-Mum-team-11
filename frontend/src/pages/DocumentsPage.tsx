import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileUp, GitCompareArrows, Upload } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Kv,
  PageHeader,
  Pagination,
  Panel,
  Select,
  SkeletonRows,
  StatusBadge,
  Tag,
  inputClass,
} from "../components/ui";
import { useDebounce } from "../hooks/useDebounce";
import { ApiError, api } from "../services/api";
import type { DocumentFamily, UploadJob, Version } from "../types/api";
import { formatBytes, formatDate, formatDateTime } from "../utils/format";

const JOB_LABEL: Record<UploadJob["status"], string> = { queued: "Queued", processing: "Processing", indexed: "Indexed", failed: "Failed" };

export default function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [regulator, setRegulator] = useState("");
  const [page, setPage] = useState(1);
  const [uploadOpen, setUploadOpen] = useState(false);
  const debouncedQ = useDebounce(q, 250);
  const openId = params.get("open") ? Number(params.get("open")) : null;

  useEffect(() => setPage(1), [debouncedQ, regulator]);

  const docs = useQuery({
    queryKey: ["documents", debouncedQ, regulator, page],
    queryFn: () => api.documents({ q: debouncedQ, regulator: regulator ? [regulator] : [], page, page_size: 20 }),
    placeholderData: keepPreviousData,
  });
  const all = useQuery({ queryKey: ["documents", "all-regulators"], queryFn: () => api.documents({ page_size: 100 }), staleTime: 60_000 });
  const regulators = Array.from(new Set((all.data?.items ?? []).map((d) => d.regulator))).sort();

  return (
    <div>
      <PageHeader
        title="Document repository"
        description="Every regulatory document and version in the repository. Uploading a new version keeps the previous one, re-indexes the text and creates a What's New update."
        actions={
          <Button variant="primary" icon={<Upload className="h-4 w-4" />} onClick={() => setUploadOpen(true)}>
            Upload document
          </Button>
        }
      />

      <Panel padded={false}>
        <div className="flex flex-wrap gap-3 border-b border-line px-5 py-3.5">
          <input
            className={clsx(inputClass, "max-w-xs")}
            placeholder="Filter by title, file or regulator"
            aria-label="Filter documents"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Select
            label="Regulator"
            className="w-auto"
            value={regulator}
            onChange={setRegulator}
            options={[{ value: "", label: "All regulators" }, ...regulators.map((r) => ({ value: r, label: r }))]}
          />
        </div>
        {docs.isLoading && <div className="p-5"><SkeletonRows rows={6} /></div>}
        {docs.isError && <div className="p-5"><ErrorState error={docs.error} onRetry={() => docs.refetch()} /></div>}
        {docs.data && docs.data.items.length === 0 && (
          <EmptyState title="No documents match" action={<Button onClick={() => { setQ(""); setRegulator(""); }}>Clear filters</Button>}>
            Change the filters, or upload a document to add it to the repository.
          </EmptyState>
        )}
        {docs.data && docs.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs text-muted">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Document</th>
                  <th className="px-3 py-2.5 font-medium">Regulator</th>
                  <th className="px-3 py-2.5 font-medium">Jurisdiction</th>
                  <th className="px-3 py-2.5 font-medium">Category</th>
                  <th className="px-3 py-2.5 font-medium">Effective</th>
                  <th className="px-3 py-2.5 font-medium">Latest version</th>
                  <th className="px-3 py-2.5 font-medium">State</th>
                  <th className="px-5 py-2.5 font-medium">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {docs.data.items.map((d) => (
                  <DocumentRow key={d.id} doc={d} onOpen={() => setParams({ open: String(d.id) })} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {docs.data && (
          <div className="border-t border-line px-5 py-3">
            <Pagination page={page} totalPages={Math.ceil(docs.data.total / docs.data.page_size)} total={docs.data.total} onChange={setPage} label="documents" />
          </div>
        )}
      </Panel>

      <RecentUploads />

      <Drawer open={uploadOpen} onClose={() => setUploadOpen(false)} title="Upload a regulatory document" width="max-w-xl">
        <UploadForm families={all.data?.items ?? []} onDone={() => setUploadOpen(false)} />
      </Drawer>
      <Drawer open={openId !== null} onClose={() => setParams({})} title={<DocumentTitle id={openId} />}>
        {openId !== null && <DocumentDetailView id={openId} />}
      </Drawer>
    </div>
  );
}

function DocumentRow({ doc, onOpen }: { doc: DocumentFamily; onOpen: () => void }) {
  const v = doc.latest_version;
  return (
    <tr className="cursor-pointer hover:bg-sunken/60" onClick={onOpen}>
      <td className="px-5 py-3">
        <button className="text-left font-medium text-ink hover:text-accent" onClick={(e) => { e.stopPropagation(); onOpen(); }}>
          {doc.title}
        </button>
        <div className="text-xs text-faint">{v?.file_name}</div>
      </td>
      <td className="px-3 py-3">{doc.regulator}</td>
      <td className="px-3 py-3">{doc.jurisdiction ?? "—"}</td>
      <td className="px-3 py-3">{doc.category ?? "—"}</td>
      <td className="px-3 py-3 whitespace-nowrap">{formatDate(v?.effective_date)}</td>
      <td className="px-3 py-3">
        {v && <Tag tone="version">{v.version_label}</Tag>}
        {doc.version_count > 1 && <span className="ml-1.5 text-xs text-faint">{doc.version_count} versions</span>}
      </td>
      <td className="px-3 py-3">{v && <StatusBadge status={v.status} label={v.status === "indexed" ? "Indexed" : undefined} />}</td>
      <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDate(v?.uploaded_at)}</td>
    </tr>
  );
}

function DocumentTitle({ id }: { id: number | null }) {
  const q = useQuery({ queryKey: ["document", id], queryFn: () => api.document(id!), enabled: id !== null });
  return <>{q.data?.title ?? "Document"}</>;
}

function DocumentDetailView({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["document", id], queryFn: () => api.document(id) });
  if (q.isLoading) return <SkeletonRows rows={5} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const doc = q.data!;
  const versions = [...doc.versions].reverse();
  return (
    <div className="space-y-6">
      <Kv
        items={[
          { label: "Regulator", value: doc.regulator },
          { label: "Jurisdiction", value: doc.jurisdiction ?? "—" },
          { label: "Category", value: doc.category ?? "—" },
          { label: "Versions", value: doc.versions.length },
        ]}
      />
      <div>
        <h3 className="mb-3 font-semibold">Version history</h3>
        <ol className="relative space-y-4 border-l border-line pl-5">
          {versions.map((v, idx) => (
            <VersionEntry key={v.id} v={v} previous={versions[idx + 1]} />
          ))}
        </ol>
      </div>
    </div>
  );
}

function VersionEntry({ v, previous }: { v: Version; previous?: Version }) {
  return (
    <li className="relative">
      <span className={clsx("absolute -left-[26px] top-1.5 h-3 w-3 rounded-full border-2 border-surface", v.is_latest ? "bg-accent" : "bg-faint")} aria-hidden />
      <div className="rounded-lg border border-line p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone="version">{v.version_label}</Tag>
          {v.is_latest && <Tag tone="accent">Latest</Tag>}
          <StatusBadge status={v.status} label={v.status === "indexed" ? "Indexed" : undefined} />
          <span className="ml-auto text-xs text-faint">{formatDateTime(v.uploaded_at)}</span>
        </div>
        <p className="mt-2 break-all text-sm font-medium">{v.file_name}</p>
        <p className="mt-1 text-xs text-muted">
          {v.source_type.toUpperCase()}, {formatBytes(v.file_size)}
          {v.page_count ? `, ${v.page_count} pages` : ""}, {v.paragraph_count} clauses, effective {formatDate(v.effective_date)}, {v.origin === "seed" ? "supplied dataset" : "uploaded"}
        </p>
        {v.status_detail && <p className="mt-2 text-sm text-fail">{v.status_detail}</p>}
        {v.warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-warn">
            {v.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        )}
        {v.metadata_notes.length > 0 && (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer">Metadata normalisation ({v.metadata_notes.length})</summary>
            <ul className="mt-1 list-disc pl-5">
              {v.metadata_notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </details>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to={`/viewer/${v.id}`} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-sunken">
            Preview
          </Link>
          <Link to={`/search?scope=version&version=${v.id}`} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-sunken">
            Search this version
          </Link>
          {previous && (
            <Link to={`/compare?base=${previous.id}&target=${v.id}`} className="inline-flex items-center gap-1.5 rounded-md bg-version-soft px-3 py-1.5 text-sm font-medium text-version hover:bg-version-soft/70">
              <GitCompareArrows className="h-4 w-4" /> Compare with {previous.version_label}
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

function RecentUploads() {
  const jobs = useQuery({ queryKey: ["upload-jobs"], queryFn: api.uploadJobs, refetchInterval: (q) => (q.state.data?.some((j) => j.status === "queued" || j.status === "processing") ? 1500 : 15000) });
  if (!jobs.data || jobs.data.length === 0) return null;
  return (
    <Panel className="mt-6" title="Recent uploads" padded={false}>
      <ul className="divide-y divide-line">
        {jobs.data.map((j) => (
          <li key={j.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
            <StatusBadge status={j.status} label={JOB_LABEL[j.status]} />
            <span className="font-medium">{j.file_name}</span>
            <span className={clsx("flex-1", j.status === "failed" ? "text-fail" : "text-muted")}>{j.detail ?? ""}</span>
            {j.version_id && (
              <Link to={`/viewer/${j.version_id}`} className="text-accent hover:underline">
                Open
              </Link>
            )}
            <span className="text-xs text-faint">{formatDateTime(j.created_at)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function UploadForm({ families, onDone }: { families: DocumentFamily[]; onDone: () => void }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [mode, setMode] = useState<"new" | "version">("new");
  const [documentId, setDocumentId] = useState("");
  const [regulator, setRegulator] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [category, setCategory] = useState("");
  const [effective, setEffective] = useState("");
  const [versionLabel, setVersionLabel] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);

  const match = useQuery({ queryKey: ["match", file?.name], queryFn: () => api.matchFamily(file!.name), enabled: !!file });
  useEffect(() => {
    const best = match.data?.find((m) => m.reason === "same file name stem");
    if (best) {
      setMode("version");
      setDocumentId(String(best.document_id));
      setVersionLabel(best.suggested_version_label);
    }
  }, [match.data]);

  const job = useQuery({
    queryKey: ["upload-job", jobId],
    queryFn: () => api.uploadJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && ["indexed", "failed"].includes(q.state.data.status) ? false : 1000),
  });
  useEffect(() => {
    if (!job.data) return;
    if (job.data.status === "indexed") {
      toast.success(`Indexed ${job.data.file_name}`, { description: job.data.detail ?? undefined });
      ["documents", "document", "alerts", "dashboard", "upload-jobs", "search-filters"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    } else if (job.data.status === "failed") {
      toast.error(`Upload failed: ${job.data.file_name}`, { description: job.data.detail ?? undefined });
      qc.invalidateQueries({ queryKey: ["upload-jobs"] });
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file!);
      if (mode === "version") form.append("document_id", documentId);
      else form.append("regulator", regulator);
      if (jurisdiction) form.append("jurisdiction", jurisdiction);
      if (category) form.append("category", category);
      if (effective) form.append("effective_date", effective);
      if (versionLabel) form.append("version_label", versionLabel);
      return api.upload(form);
    },
    onSuccess: (res) => {
      setJobId(res.job_id);
      qc.invalidateQueries({ queryKey: ["upload-jobs"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Upload failed"),
  });

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };
  const canSubmit = !!file && (mode === "version" ? !!documentId : regulator.trim().length > 0);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSubmit) upload.mutate();
  };

  if (jobId) {
    const status = job.data?.status ?? "queued";
    return (
      <div className="space-y-4">
        <ol className="space-y-2">
          {(["queued", "processing", "indexed"] as const).map((s) => {
            const order = ["queued", "processing", "indexed"];
            const reached = status === "failed" ? s === "queued" : order.indexOf(status) >= order.indexOf(s);
            return (
              <li key={s} className={clsx("flex items-center gap-3 text-sm", reached ? "text-ink" : "text-faint")}>
                <span className={clsx("h-2.5 w-2.5 rounded-full", reached ? "bg-accent" : "bg-line")} />
                {JOB_LABEL[s]}
              </li>
            );
          })}
          {status === "failed" && (
            <li className="flex items-center gap-3 text-sm text-fail">
              <span className="h-2.5 w-2.5 rounded-full bg-fail" /> Failed
            </li>
          )}
        </ol>
        {job.data?.detail && <p className={clsx("text-sm", status === "failed" ? "text-fail" : "text-muted")}>{job.data.detail}</p>}
        <div className="flex gap-2">
          {status === "indexed" && job.data?.version_id && (
            <Link to={`/whats-new`} className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-sm font-medium text-white" onClick={onDone}>
              See the update
            </Link>
          )}
          <Button onClick={() => { setJobId(null); setFile(null); }}>Upload another</Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        className={clsx(
          "flex cursor-pointer flex-col items-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-accent bg-accent-soft" : "border-line hover:border-accent/60",
        )}
      >
        <FileUp className="mb-2 h-7 w-7 text-faint" aria-hidden />
        {file ? (
          <>
            <p className="font-medium">{file.name}</p>
            <p className="text-xs text-muted">{formatBytes(file.size)}. Click to choose a different file.</p>
          </>
        ) : (
          <>
            <p className="font-medium">Drop a PDF, HTML or TXT file here</p>
            <p className="text-xs text-muted">or click to browse (25 MB maximum)</p>
          </>
        )}
        <input ref={inputRef} type="file" accept=".pdf,.html,.htm,.txt" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">This file is</legend>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "new"} onChange={() => setMode("new")} /> A new document
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "version"} onChange={() => setMode("version")} /> A new version of an existing document
          </label>
        </div>
      </fieldset>

      {mode === "version" ? (
        <Field label="Existing document" hint={match.data?.length ? `Suggested from the file name: ${match.data[0].title}` : undefined}>
          <Select
            label="Existing document"
            value={documentId}
            onChange={(v) => {
              setDocumentId(v);
              const m = match.data?.find((x) => String(x.document_id) === v);
              if (m) setVersionLabel(m.suggested_version_label);
            }}
            options={[{ value: "", label: "Choose a document…" }, ...families.map((f) => ({ value: String(f.id), label: `${f.title} (${f.regulator}, latest ${f.latest_version?.version_label ?? "—"})` }))]}
          />
        </Field>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Regulator">
            <input className={inputClass} value={regulator} onChange={(e) => setRegulator(e.target.value)} placeholder="e.g. ESMA" required />
          </Field>
          <Field label="Jurisdiction">
            <input className={inputClass} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="e.g. EU" />
          </Field>
          <Field label="Category">
            <input className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Trade reporting" />
          </Field>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Effective date" hint={mode === "version" ? "Leave empty to keep the previous version's date" : undefined}>
          <input type="date" className={inputClass} value={effective} onChange={(e) => setEffective(e.target.value)} />
        </Field>
        <Field label="Version label" hint="Leave empty to number it automatically">
          <input className={inputClass} value={versionLabel} onChange={(e) => setVersionLabel(e.target.value)} placeholder="v3.0" />
        </Field>
      </div>
      <Button type="submit" variant="primary" loading={upload.isPending} disabled={!canSubmit} icon={<Upload className="h-4 w-4" />}>
        Upload and index
      </Button>
    </form>
  );
}
