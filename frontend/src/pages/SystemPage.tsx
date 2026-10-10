import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, ExternalLink, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, ErrorState, Field, Kv, PageHeader, Panel, SkeletonRows, StatusBadge, inputClass } from "../components/ui";
import { ApiError, api, getApiToken, setApiToken } from "../services/api";
import type { HealthCheck } from "../types/api";
import { formatDateTime, formatNumber } from "../utils/format";

function Check({ check, label }: { check: HealthCheck | null | undefined; label: string }) {
  const ok = !!check?.ok;
  return (
    <div className="flex items-start gap-3 py-2">
      {ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 flex-none text-pass" /> : <XCircle className="mt-0.5 h-4 w-4 flex-none text-fail" />}
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        <div className="break-words text-xs text-muted">{check?.detail ?? "No data"}</div>
      </div>
    </div>
  );
}

export default function SystemPage() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["system"], queryFn: api.system, refetchInterval: 5000 });
  const reimport = useMutation({
    mutationFn: api.runImport,
    onSuccess: () => {
      toast.success("Dataset import started");
      qc.invalidateQueries({ queryKey: ["system"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start import"),
  });
  const [token, setToken] = useState(getApiToken());

  if (status.isLoading) return <SkeletonRows rows={6} />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  const s = status.data!;
  const imp = s.import;

  return (
    <div>
      <PageHeader
        title="System health"
        description={`Live status of every service and dependency, refreshed every 5 seconds. Last check ${formatDateTime(s.generated_at)}.`}
        actions={<StatusBadge status={s.overall} label={s.overall === "ok" ? "All systems operational" : "Degraded"} />}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Infrastructure">
          <Check check={s.elasticsearch} label="Elasticsearch" />
          <Check check={s.postgresql} label="PostgreSQL" />
          <Check check={s.rules} label="Rule configuration" />
          <Check check={{ ok: true, detail: s.gateway.api_token_required ? "Bearer token required for mutating operations" : "Open (no API token configured)" }} label="API gateway" />
        </Panel>
        <Panel title="Search index">
          {s.index ? (
            <Kv
              items={[
                { label: "Index", value: s.index.index },
                { label: "Paragraphs", value: formatNumber(s.index.paragraphs_total) },
                { label: "Latest-version paragraphs", value: formatNumber(s.index.paragraphs_latest) },
                { label: "Document versions", value: formatNumber(s.index.versions_indexed) },
                { label: "Documents", value: formatNumber(s.index.documents_indexed) },
              ]}
            />
          ) : (
            <p className="text-sm text-fail">Index statistics unavailable.</p>
          )}
        </Panel>
        <Panel title="API documentation">
          <div className="space-y-2 text-sm">
            <a href={s.links.swagger_ui} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-accent hover:underline">
              <ExternalLink className="h-4 w-4" /> Swagger UI
            </a>
            <a href={s.links.openapi} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-accent hover:underline">
              <ExternalLink className="h-4 w-4" /> OpenAPI specification (JSON)
            </a>
          </div>
          <form
            className="mt-5"
            onSubmit={(e) => {
              e.preventDefault();
              setApiToken(token.trim());
              toast.success(token.trim() ? "API token saved in this browser" : "API token cleared");
            }}
          >
            <Field label="API token" hint="Only needed when the gateway is started with API_TOKEN. Stored in this browser only.">
              <input type="password" className={inputClass} value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
            </Field>
            <Button className="mt-2" size="sm" type="submit">Save token</Button>
          </form>
        </Panel>
      </div>

      <Panel className="mt-6" title="Services" padded={false}>
        <div className="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
          {s.services.map((svc) => (
            <div key={svc.name} className="p-5">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold capitalize">{svc.name} service</h3>
                <StatusBadge status={svc.status} label={svc.status === "ok" ? "Healthy" : svc.status === "unreachable" ? "Unreachable" : "Degraded"} />
              </div>
              <p className="mt-0.5 text-xs text-faint">
                {svc.url}, {svc.latency_ms} ms
              </p>
              {svc.error && <p className="mt-2 text-sm text-fail">{svc.error}</p>}
              <div className="mt-2 divide-y divide-line/60">
                {Object.entries(svc.checks).map(([name, check]) => (
                  <Check key={name} check={check} label={name.replace(/_/g, " ")} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        className="mt-6"
        title="Dataset import"
        actions={
          <Button size="sm" icon={<RefreshCw className="h-4 w-4" />} loading={reimport.isPending} onClick={() => reimport.mutate()}>
            Re-run import
          </Button>
        }
      >
        {imp ? (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <StatusBadge status={imp.status} label={imp.status.replace(/_/g, " ")} />
              <span className="text-muted">
                {imp.files_processed} indexed, {imp.files_skipped} unchanged, {imp.files_failed} failed of {imp.files_total} files
              </span>
              <span className="text-faint">started {formatDateTime(imp.started_at)}</span>
            </div>
            {imp.errors.length > 0 && (
              <ul className="mt-3 list-disc pl-5 text-sm text-fail">
                {imp.errors.map((e) => <li key={e}>{e}</li>)}
              </ul>
            )}
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-muted">Import log ({imp.log.length} lines)</summary>
              <pre className={clsx("scroll-thin mt-2 max-h-72 overflow-auto rounded-md bg-sunken p-3 font-mono text-xs leading-relaxed")}>{imp.log.join("\n")}</pre>
            </details>
          </>
        ) : (
          <p className="text-sm text-muted">No import has run yet.</p>
        )}
      </Panel>
    </div>
  );
}
