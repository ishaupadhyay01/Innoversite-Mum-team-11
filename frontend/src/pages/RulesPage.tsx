import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Code, ErrorState, JsonBlock, Notice, PageHeader, Panel, SkeletonRows, StatusBadge, Tag } from "../components/ui";
import { ApiError, api } from "../services/api";
import type { Rule } from "../types/api";
import { formatDateTime } from "../utils/format";

const SAMPLE = JSON.stringify(
  {
    regulator: "Demo regime",
    jurisdiction: "EU",
    rules: [
      {
        id: "DEMO-1",
        description: "Derivatives must carry a maturity date after the trade date.",
        applies_when: { "==": [{ var: "Asset_Class" }, "Derivative"] },
        logic: { ">": [{ var: "Maturity_Date" }, { substr: [{ var: "Timestamp" }, 0, 10] }] },
        impact: "Maturity_Date must be later than the execution date.",
      },
    ],
  },
  null,
  2,
);

export default function RulesPage() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const reload = useMutation({
    mutationFn: api.reloadRules,
    onSuccess: (r) => {
      toast.success(`Rules reloaded: ${r.rules} rules`, { description: r.added.length ? `Added ${r.added.join(", ")}` : undefined });
      qc.invalidateQueries({ queryKey: ["rules"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Reload failed"),
  });

  return (
    <div>
      <PageHeader
        title="Rules"
        description="Executable rules are read from the JSON files in data/rules. Add or edit a file, then reload; no code changes are needed. The original JSON is kept and any normalisation is listed per rule."
        actions={
          <Button icon={<RefreshCw className="h-4 w-4" />} loading={reload.isPending} onClick={() => reload.mutate()}>
            Reload rule files
          </Button>
        }
      />
      {rules.isLoading && <SkeletonRows rows={6} />}
      {rules.isError && <ErrorState error={rules.error} onRetry={() => rules.refetch()} />}
      {rules.data && (
        <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
          <div className="space-y-6">
            {rules.data.load_errors.length > 0 && <Notice tone="warn">{rules.data.load_errors.join("; ")}</Notice>}
            {rules.data.rule_sets.map((rs) => (
              <Panel
                key={rs.file_name}
                title={`${rs.regulator} (${rs.jurisdiction ?? "—"})`}
                description={`${rs.file_name}, ${rs.rule_count} rules`}
                actions={<StatusBadge status={rs.valid ? "ok" : "failed"} label={rs.valid ? "Valid" : "Invalid"} />}
                padded={false}
              >
                <ul className="divide-y divide-line">
                  {rs.rules.map((r) => (
                    <RuleRow key={r.id} rule={r} />
                  ))}
                </ul>
              </Panel>
            ))}
          </div>
          <div className="space-y-6">
            <Panel title="Reporting schema">
              <p className="text-sm text-muted">{rules.data.schema.source}, {rules.data.schema.fields.length} fields, {rules.data.schema.required.length} required</p>
              {rules.data.schema.normalization_notes.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted">
                  {rules.data.schema.normalization_notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              )}
              <p className="mt-3 text-xs text-faint">Loaded {formatDateTime(rules.data.loaded_at)}</p>
            </Panel>
            <Validator />
          </div>
        </div>
      )}
    </div>
  );
}

function RuleRow({ rule }: { rule: Rule }) {
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{rule.id}</span>
        {!rule.valid && <StatusBadge status="failed" label="Invalid" />}
        {rule.applies_when_source === "overlay" && <Tag tone="version">Applicability from overlay</Tag>}
        {rule.normalization_notes.length > 0 && <Tag tone="warn">{rule.normalization_notes.length} normalisation note{rule.normalization_notes.length > 1 ? "s" : ""}</Tag>}
      </div>
      <p className="mt-1 text-ink">{rule.description}</p>
      <div className="mt-2 space-y-1 text-sm">
        <div><span className="text-muted">Logic </span><Code>{rule.logic_text}</Code></div>
        {rule.applies_when_text && <div><span className="text-muted">Applies when </span><Code>{rule.applies_when_text}</Code></div>}
      </div>
      {(rule.errors.length > 0 || rule.warnings.length > 0) && (
        <ul className="mt-2 list-disc pl-5 text-sm text-warn">
          {[...rule.errors, ...rule.warnings].map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted">Details</summary>
        <div className="mt-2 space-y-3">
          {rule.normalization_notes.length > 0 && (
            <ul className="list-disc pl-5 text-muted">
              {rule.normalization_notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}
          <div>
            <p className="mb-1 text-xs text-faint">Original logic ({rule.rule_source})</p>
            <JsonBlock value={rule.source_logic} />
          </div>
          <div>
            <p className="mb-1 text-xs text-faint">Evaluated logic</p>
            <JsonBlock value={rule.logic} />
          </div>
        </div>
      </details>
    </li>
  );
}

function Validator() {
  const [text, setText] = useState(SAMPLE);
  const [parseError, setParseError] = useState<string | null>(null);
  const validate = useMutation({ mutationFn: (body: unknown) => api.validateRules(body) });
  const run = () => {
    try {
      const body = JSON.parse(text);
      setParseError(null);
      validate.mutate(body);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON");
    }
  };
  const result = validate.data as undefined | { valid: boolean; errors: string[]; rules: Rule[] };
  return (
    <Panel title="Validate a rule set" description="Checks structure, operators, field names and regex patterns. Nothing is saved.">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        aria-label="Rule set JSON"
        className="h-64 w-full rounded-md border border-line bg-sunken p-3 font-mono text-[12.5px] leading-relaxed text-ink focus:border-accent focus:outline-none"
      />
      <Button className="mt-3" variant="primary" loading={validate.isPending} onClick={run}>
        Validate
      </Button>
      {parseError && <p className="mt-3 text-sm text-fail">JSON parse error: {parseError}</p>}
      {validate.isError && <div className="mt-3"><ErrorState error={validate.error} /></div>}
      {result && (
        <div className="mt-4 space-y-2 text-sm">
          <StatusBadge status={result.valid ? "ok" : "failed"} label={result.valid ? "Valid rule set" : "Invalid rule set"} />
          {result.errors.map((e) => <p key={e} className="text-fail">{e}</p>)}
          {result.rules.map((r) => (
            <div key={r.id} className="rounded-md border border-line p-3">
              <p className="font-medium">{r.id}</p>
              <p className="mt-1"><Code>{r.logic_text}</Code></p>
              {[...r.errors, ...r.warnings].map((e) => <p key={e} className={r.errors.includes(e) ? "text-fail" : "text-warn"}>{e}</p>)}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
