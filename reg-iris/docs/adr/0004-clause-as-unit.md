# ADR 0004 — The clause is the unit of storage, search, diff and citation

**Status:** accepted

**Context.** Users need "the exact paragraph or clause with a clickable citation"; What's New needs a short diff;
rules need traceability to a clause.

**Decision.** Ingestion segments every version into clauses (`Paragraph N`, `Article N`, `Section N`, `Qn`, HTML
sections) with page spans and anchors. Search indexes one document per clause; diffs align clauses by reference (then by
similarity for renumbering); rule links point to clauses.

**Consequences.** Precise citations and readable diffs. Documents without recognisable headings fall back to
paragraph blocks (`¶N`) — extend `HEADING_PATTERNS` per regulator style.
