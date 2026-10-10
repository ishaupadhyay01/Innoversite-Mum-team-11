import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ingestionApi } from "@/api/ingestion";
import type { MatchSuggestionResponse } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/Feedback";
import { FilePicker } from "@/components/ui/FilePicker";

type Target = { kind: "new" } | { kind: "version"; documentId: string };

/**
 * Two-step upload: (1) pre-check → exact duplicate / similar documents are suggested,
 * (2) user confirms "new document" or "new version of X".
 */
export function UploadDocumentDialog({ onClose, fixedDocumentId }: { onClose: () => void; fixedDocumentId?: string }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState({ regulator: "", title: "", jurisdiction: "", category: "", effective_date: "", version_label: "" });
  const [suggestions, setSuggestions] = useState<MatchSuggestionResponse | null>(null);
  const [target, setTarget] = useState<Target>(fixedDocumentId ? { kind: "version", documentId: fixedDocumentId } : { kind: "new" });

  const check = useMutation({
    mutationFn: () => ingestionApi.matchSuggestions(file!, meta.regulator || undefined, meta.title || undefined),
    onSuccess: (res) => {
      setSuggestions(res);
      const best = res.candidates[0];
      if (!fixedDocumentId && res.recommendation === "NEW_VERSION" && best) setTarget({ kind: "version", documentId: best.document_id });
    },
  });

  const upload = useMutation({
    mutationFn: () =>
      target.kind === "new"
        ? ingestionApi.uploadNew({ file: file!, ...meta })
        : ingestionApi.uploadVersion(target.documentId, file!, meta.version_label, meta.effective_date),
    onSuccess: (res) => {
      void qc.invalidateQueries();
      onClose();
      navigate(`/documents/${res.document.id}`);
    },
  });

  const set = (k: keyof typeof meta) => (e: React.ChangeEvent<HTMLInputElement>) => setMeta({ ...meta, [k]: e.target.value });
  const isDuplicate = suggestions?.recommendation === "DUPLICATE";

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/40 p-6" role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-semibold">{fixedDocumentId ? "Upload new version" : "Upload regulatory document"}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-canvas"><X className="h-4 w-4" /></button>
        </header>
        <div className="space-y-4 p-5">
          <FilePicker accept=".pdf,.html,.htm,.txt" label="Drop a PDF, HTML or TXT file, or click to browse" file={file}
            onFile={(f) => { setFile(f); setSuggestions(null); }} />
          <div className="grid grid-cols-2 gap-3">
            {!fixedDocumentId && (
              <>
                <div><label className="label">Regulator *</label><input className="input" value={meta.regulator} onChange={set("regulator")} placeholder="MiFID II" /></div>
                <div><label className="label">Title</label><input className="input" value={meta.title} onChange={set("title")} placeholder="Defaults to file name" /></div>
                <div><label className="label">Jurisdiction</label><input className="input" value={meta.jurisdiction} onChange={set("jurisdiction")} placeholder="EU" /></div>
                <div><label className="label">Category</label><input className="input" value={meta.category} onChange={set("category")} placeholder="Trade reporting" /></div>
              </>
            )}
            <div><label className="label">Effective date</label><input type="date" className="input" value={meta.effective_date} onChange={set("effective_date")} /></div>
            <div><label className="label">Version label</label><input className="input" value={meta.version_label} onChange={set("version_label")} placeholder="auto (v1.0, v2.0…)" /></div>
          </div>

          {suggestions && (
            <div className="rounded-md border border-line bg-canvas p-3 text-sm">
              {isDuplicate && suggestions.exact_duplicate && (
                <p className="text-fail">
                  Exact duplicate of <strong>{suggestions.exact_duplicate.title}</strong> ({suggestions.exact_duplicate.version_label}). Upload blocked.
                </p>
              )}
              {!isDuplicate && (
                <>
                  <p className="mb-2 font-medium">
                    {suggestions.candidates.length ? "Possible matches — is this an update of an existing document?" : "No similar documents found."}
                  </p>
                  <div className="space-y-1.5">
                    {!fixedDocumentId && (
                      <label className="flex items-center gap-2">
                        <input type="radio" checked={target.kind === "new"} onChange={() => setTarget({ kind: "new" })} />
                        Create a <strong>new document</strong>
                      </label>
                    )}
                    {suggestions.candidates.map((c) => (
                      <label key={c.document_id} className="flex items-start gap-2">
                        <input type="radio" className="mt-1" disabled={!!fixedDocumentId && c.document_id !== fixedDocumentId}
                          checked={target.kind === "version" && target.documentId === c.document_id}
                          onChange={() => setTarget({ kind: "version", documentId: c.document_id })} />
                        <span>
                          New version of <strong>{c.title}</strong> <Badge tone="brand">{c.regulator}</Badge>{" "}
                          <span className="font-mono text-xs">{(c.score * 100).toFixed(0)}% match</span>
                          <span className="block text-xs text-ink-soft">{c.reasons.join(" · ")}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
          <ErrorBanner error={check.error ?? upload.error} />
        </div>
        <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          {!suggestions ? (
            <Button disabled={!file || (!fixedDocumentId && !meta.regulator) || check.isPending} onClick={() => check.mutate()}>
              {check.isPending ? "Checking…" : "Check for duplicates"}
            </Button>
          ) : (
            <Button disabled={isDuplicate || upload.isPending} onClick={() => upload.mutate()}>
              {upload.isPending ? "Uploading…" : target.kind === "new" ? "Upload new document" : "Upload as new version"}
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}
