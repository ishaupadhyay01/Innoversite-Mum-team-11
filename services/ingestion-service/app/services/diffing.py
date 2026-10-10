"""Deterministic version comparison of two parsed documents.

Algorithm (no AI, no semantic claims):

1. Each clause is reduced to its normalised full text.
2. ``difflib.SequenceMatcher`` aligns the two clause sequences, giving
   equal / insert / delete / replace blocks.
3. Inside a replace block, old and new clauses are paired in order when
   their headings match or their text similarity ratio is at least
   ``MODIFIED_THRESHOLD``; paired clauses are *modified*, the rest are
   *removed* or *added*.
4. Modified clauses get a word-level inline diff.

The summary is assembled only from these measured differences. A
"modified" label means "textually similar but not identical" — it says
nothing about legal significance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from iris_shared.text import normalize_inline

MODIFIED_THRESHOLD = 0.55
_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)
_VERSION_TAG_RE = re.compile(r"\s*\((v\d+(\.\d+)*)\)\s*$", re.IGNORECASE)


@dataclass
class ClauseRef:
    ordinal: int
    heading: str | None
    body: str
    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    anchor: str | None = None

    @property
    def text(self) -> str:
        if self.heading and self.body:
            return f"{self.heading}\n{self.body}"
        return self.heading or self.body

    def location(self) -> str:
        if self.page_start:
            if self.page_end and self.page_end != self.page_start:
                return f"pp. {self.page_start}–{self.page_end}"
            return f"p. {self.page_start}"
        if self.line_start:
            return f"lines {self.line_start}–{self.line_end or self.line_start}"
        if self.anchor:
            return f"#{self.anchor}"
        return f"clause {self.ordinal}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "heading": self.heading,
            "body": self.body,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "anchor": self.anchor,
            "location": self.location(),
        }


@dataclass
class DiffRow:
    change: str  # unchanged | added | removed | modified
    old: ClauseRef | None
    new: ClauseRef | None
    similarity: float | None = None
    inline: list[dict[str, str]] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "change": self.change,
            "old": self.old.as_dict() if self.old else None,
            "new": self.new.as_dict() if self.new else None,
            "similarity": round(self.similarity, 3) if self.similarity is not None else None,
            "inline": self.inline,
        }


@dataclass
class DiffResult:
    rows: list[DiffRow]
    stats: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    change_types: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats,
            "summary": self.summary,
            "change_types": self.change_types,
            "rows": [r.as_dict() for r in self.rows],
        }


def _key(clause: ClauseRef) -> str:
    return normalize_inline(clause.text).lower()


def _heading_key(heading: str | None) -> str | None:
    if not heading:
        return None
    return _VERSION_TAG_RE.sub("", normalize_inline(heading)).lower()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def inline_diff(old: str, new: str) -> list[dict[str, str]]:
    """Word-level diff segments: [{"op": "equal"|"delete"|"insert", "text": ...}]."""
    a = _TOKEN_RE.findall(old)
    b = _TOKEN_RE.findall(new)
    segments: list[dict[str, str]] = []

    def push(op: str, text: str) -> None:
        if not text:
            return
        if segments and segments[-1]["op"] == op:
            segments[-1]["text"] += text
        else:
            segments.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            push("equal", "".join(a[i1:i2]))
        elif tag == "delete":
            push("delete", "".join(a[i1:i2]))
        elif tag == "insert":
            push("insert", "".join(b[j1:j2]))
        else:
            push("delete", "".join(a[i1:i2]))
            push("insert", "".join(b[j1:j2]))
    return segments


def _pair_block(old: list[ClauseRef], new: list[ClauseRef]) -> list[DiffRow]:
    rows: list[DiffRow] = []
    j_start = 0
    used_new: set[int] = set()
    pending_old: list[ClauseRef] = []
    for o in old:
        best_j, best_ratio = None, 0.0
        for j in range(j_start, len(new)):
            if j in used_new:
                continue
            same_heading = _heading_key(o.heading) is not None and _heading_key(o.heading) == _heading_key(new[j].heading)
            ratio = similarity(_key(o), _key(new[j]))
            if same_heading:
                ratio = max(ratio, MODIFIED_THRESHOLD)
            if ratio > best_ratio:
                best_j, best_ratio = j, ratio
        if best_j is not None and best_ratio >= MODIFIED_THRESHOLD:
            # Emit unmatched new clauses that come before the pair, then the old ones skipped.
            for j in range(j_start, best_j):
                if j not in used_new:
                    rows.append(DiffRow("added", None, new[j]))
                    used_new.add(j)
            for po in pending_old:
                rows.append(DiffRow("removed", po, None))
            pending_old = []
            n = new[best_j]
            rows.append(DiffRow("modified", o, n, similarity=similarity(_key(o), _key(n)), inline=inline_diff(o.text, n.text)))
            used_new.add(best_j)
            j_start = best_j + 1
        else:
            pending_old.append(o)
    for po in pending_old:
        rows.append(DiffRow("removed", po, None))
    for j in range(len(new)):
        if j not in used_new:
            rows.append(DiffRow("added", None, new[j]))
    return rows


def compare(old: list[ClauseRef], new: list[ClauseRef]) -> DiffResult:
    matcher = SequenceMatcher(None, [_key(c) for c in old], [_key(c) for c in new], autojunk=False)
    rows: list[DiffRow] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for o, n in zip(old[i1:i2], new[j1:j2], strict=True):
                rows.append(DiffRow("unchanged", o, n, similarity=1.0))
        elif tag == "delete":
            rows.extend(DiffRow("removed", o, None) for o in old[i1:i2])
        elif tag == "insert":
            rows.extend(DiffRow("added", None, n) for n in new[j1:j2])
        else:
            rows.extend(_pair_block(old[i1:i2], new[j1:j2]))

    stats = {k: sum(1 for r in rows if r.change == k) for k in ("unchanged", "added", "removed", "modified")}
    stats["old_clauses"] = len(old)
    stats["new_clauses"] = len(new)
    change_types: list[str] = []
    if stats["added"]:
        change_types.append("Added Clause")
    if stats["removed"]:
        change_types.append("Removed Clause")
    if stats["modified"]:
        change_types.append("Modified Clause")
    return DiffResult(rows=rows, stats=stats, summary=summarize(rows, stats), change_types=change_types)


def _label(clause: ClauseRef) -> str:
    title = clause.heading or (clause.body[:60] + ("…" if len(clause.body) > 60 else ""))
    return f"“{title}” ({clause.location()})"


def summarize(rows: list[DiffRow], stats: dict[str, int], max_items: int = 3) -> str:
    if not (stats.get("added") or stats.get("removed") or stats.get("modified")):
        return "No textual differences detected between the two versions."
    parts: list[str] = []
    for change, noun in (("added", "added"), ("removed", "removed"), ("modified", "modified")):
        items = [r for r in rows if r.change == change]
        if not items:
            continue
        clauses = [_label(r.new if change != "removed" else r.old) for r in items]  # type: ignore[arg-type]
        shown = "; ".join(clauses[:max_items])
        more = f"; and {len(clauses) - max_items} more" if len(clauses) > max_items else ""
        word = "clause" if len(items) == 1 else "clauses"
        parts.append(f"{len(items)} {word} {noun}: {shown}{more}")
    unchanged = stats.get("unchanged", 0)
    parts.append(f"{unchanged} unchanged")
    return ". ".join(parts) + "."
