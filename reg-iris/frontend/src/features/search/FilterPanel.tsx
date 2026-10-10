import type { Facets, SearchParams } from "@/api/types";

type Filters = Pick<SearchParams, "regulator" | "jurisdiction" | "category" | "status" | "effective_from" | "effective_to">;

function MultiCheck({ label, options, selected, onChange }: {
  label: string;
  options: { value: string; count: number }[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  if (!options.length) return null;
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="space-y-1">
        {options.map((o) => (
          <label key={o.value} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(o.value)}
              onChange={(e) => onChange(e.target.checked ? [...selected, o.value] : selected.filter((s) => s !== o.value))}
            />
            <span className="flex-1">{o.value}</span>
            <span className="font-mono text-xs text-ink-faint">{o.count}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function FilterPanel({ facets, value, onChange }: { facets?: Facets; value: Filters; onChange: (f: Filters) => void }) {
  return (
    <aside className="space-y-5">
      <fieldset>
        <legend className="label">Version status</legend>
        <select className="input" value={value.status} onChange={(e) => onChange({ ...value, status: e.target.value as Filters["status"] })}>
          <option value="ACTIVE">Active versions only</option>
          <option value="INACTIVE">Superseded versions</option>
          <option value="ALL">All versions</option>
        </select>
      </fieldset>
      <MultiCheck label="Regulator" options={facets?.regulator ?? []} selected={value.regulator} onChange={(regulator) => onChange({ ...value, regulator })} />
      <MultiCheck label="Jurisdiction" options={facets?.jurisdiction ?? []} selected={value.jurisdiction} onChange={(jurisdiction) => onChange({ ...value, jurisdiction })} />
      <MultiCheck label="Category" options={facets?.category ?? []} selected={value.category} onChange={(category) => onChange({ ...value, category })} />
      <fieldset className="space-y-2">
        <legend className="label">Effective date</legend>
        <input type="date" aria-label="Effective from" className="input" value={value.effective_from ?? ""} onChange={(e) => onChange({ ...value, effective_from: e.target.value || undefined })} />
        <input type="date" aria-label="Effective to" className="input" value={value.effective_to ?? ""} onChange={(e) => onChange({ ...value, effective_to: e.target.value || undefined })} />
      </fieldset>
    </aside>
  );
}
