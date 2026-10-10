import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { SearchHit } from "@/api/types";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { fmtDate } from "@/lib/format";

/** Highlights come from the search backend with <mark> tags around matches and HTML-escaped text. */
export function SearchResultCard({ hit }: { hit: SearchHit }) {
  const c = hit.citation;
  return (
    <article className="rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">{c.regulator}</Badge>
        <span className="text-sm font-semibold">{c.clause_ref}</span>
        {c.clause_title && <span className="text-sm text-ink-soft">{c.clause_title}</span>}
        <StatusBadge status={hit.status} />
        <span className="ml-auto font-mono text-xs text-ink-faint">score {hit.score.toFixed(2)}</span>
      </div>
      <div className="mt-2 space-y-1 text-sm leading-relaxed">
        {hit.highlights.map((h, i) => (
          <p key={i} dangerouslySetInnerHTML={{ __html: `…${h}…` }} />
        ))}
      </div>
      <footer className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-2 text-xs">
        <a href={c.file_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
          {c.label} <ExternalLink className="h-3 w-3" />
        </a>
        <Link to={`/documents/${c.document_id}?version=${c.version_id}`} className="text-ink-soft hover:underline">
          View in repository
        </Link>
        <span className="ml-auto text-ink-faint">effective {fmtDate(hit.effective_date)}</span>
      </footer>
    </article>
  );
}
