import clsx from "clsx";
import { Link } from "react-router-dom";
import type { WhatsNewCard as Card } from "@/api/types";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { fmtDate, fmtDateTime } from "@/lib/format";

export function WhatsNewCard({ card, highlighted }: { card: Card; highlighted?: boolean }) {
  const s = card.summary;
  return (
    <article
      id={`card-${card.id}`}
      className={clsx("rounded-lg border bg-white p-4", highlighted ? "border-brand ring-2 ring-brand/30" : "border-line")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">{card.regulator}</Badge>
        <Badge>{card.card_type === "NEW_VERSION" ? "Updated" : "New document"}</Badge>
        <span className="text-xs text-ink-soft">Effective {fmtDate(card.effective_date)}</span>
        <span className="ml-auto text-xs text-ink-faint">{fmtDateTime(card.created_at)}</span>
      </div>
      <h3 className="mt-2 text-sm font-semibold">
        <Link to={`/documents/${card.document_id}`} className="hover:underline">
          {card.title}
        </Link>
      </h3>
      <p className="mt-1 text-sm text-ink-soft">{card.headline}</p>
      <div className="mt-3 flex gap-3 font-mono text-xs">
        <span className="text-pass">+{s.ADDED ?? 0} added</span>
        <span className="text-warn">~{s.MODIFIED ?? 0} modified</span>
        <span className="text-fail">−{s.REMOVED ?? 0} removed</span>
      </div>
      {card.highlights.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-line pt-3">
          {card.highlights.slice(0, 3).map((h) => (
            <li key={h.clause_ref} className="flex gap-2 text-sm">
              <StatusBadge status={h.change} />
              <span className="font-medium">{h.clause_ref}</span>
              <span className="truncate text-ink-soft">{h.title}</span>
              {h.page && <span className="ml-auto shrink-0 text-xs text-ink-faint">p.{h.page}</span>}
            </li>
          ))}
        </ul>
      )}
      {card.card_type === "NEW_VERSION" && (
        <Link to={`/documents/${card.document_id}?diff=${card.version_id}`} className="mt-3 inline-block text-xs font-medium text-brand hover:underline">
          View full diff →
        </Link>
      )}
    </article>
  );
}
