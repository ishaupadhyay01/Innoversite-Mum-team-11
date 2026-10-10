"""Clause-level document comparison.

Shared by Ingestion (automatic "What's New" on a new version) and Search
(user-driven comparison of any two versions or regulations).

Algorithm
1. Align clauses by ``clause_ref`` (e.g. "Paragraph 3", "Q5", "p2").
2. Unmatched clauses are paired by text similarity (>= ``rename_threshold``) to catch renumbering.
3. Paired clauses with different normalised text are MODIFIED and get a word-level diff.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import StrEnum

from .text import normalize_text


class ChangeType(StrEnum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class ClauseInput:
    clause_ref: str
    text: str
    title: str | None = None
    page: int | None = None
    clause_id: str | None = None


@dataclass
class InlineOp:
    op: str  # "equal" | "insert" | "delete"
    text: str


@dataclass
class ClauseChange:
    change: ChangeType
    clause_ref: str
    title: str | None
    old_text: str | None
    new_text: str | None
    old_page: int | None
    new_page: int | None
    similarity: float
    inline: list[InlineOp] = field(default_factory=list)


@dataclass
class DiffResult:
    changes: list[ClauseChange]

    @property
    def summary(self) -> dict[str, int]:
        counts = {c.value: 0 for c in ChangeType}
        for ch in self.changes:
            counts[ch.change.value] += 1
        return counts

    def headline(self, max_items: int = 3) -> str:
        parts = []
        for ch in self.changes:
            if ch.change is ChangeType.UNCHANGED:
                continue
            label = f"{ch.clause_ref}{f' ({ch.title})' if ch.title else ''}"
            parts.append(f"{ch.change.value.lower()} {label}")
            if len(parts) == max_items:
                break
        s = self.summary
        total = s["ADDED"] + s["REMOVED"] + s["MODIFIED"]
        if total == 0:
            return "No textual changes detected."
        more = f" and {total - len(parts)} more" if total > len(parts) else ""
        text = "; ".join(parts) + more
        return text[0].upper() + text[1:] + "."


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def inline_diff(old: str, new: str) -> list[InlineOp]:
    a, b = old.split(), new.split()
    ops: list[InlineOp] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append(InlineOp("equal", " ".join(a[i1:i2])))
        if tag in ("delete", "replace"):
            ops.append(InlineOp("delete", " ".join(a[i1:i2])))
        if tag in ("insert", "replace"):
            ops.append(InlineOp("insert", " ".join(b[j1:j2])))
    return ops


def diff_clauses(
    old: list[ClauseInput], new: list[ClauseInput], *, rename_threshold: float = 0.75, include_unchanged: bool = True
) -> DiffResult:
    old_by_ref = {c.clause_ref: c for c in old}
    new_by_ref = {c.clause_ref: c for c in new}
    pairs: list[tuple[ClauseInput | None, ClauseInput | None]] = []

    unmatched_old = [c for c in old if c.clause_ref not in new_by_ref]
    unmatched_new = [c for c in new if c.clause_ref not in old_by_ref]
    for n in new:
        if n.clause_ref in old_by_ref:
            pairs.append((old_by_ref[n.clause_ref], n))

    # Pair renumbered clauses by similarity (greedy, best first).
    for n in list(unmatched_new):
        best, best_score = None, 0.0
        for o in unmatched_old:
            score = _ratio(normalize_text(o.text), normalize_text(n.text))
            if score > best_score:
                best, best_score = o, score
        if best is not None and best_score >= rename_threshold:
            pairs.append((best, n))
            unmatched_old.remove(best)
            unmatched_new.remove(n)

    pairs += [(None, n) for n in unmatched_new]
    pairs += [(o, None) for o in unmatched_old]

    order = {c.clause_ref: i for i, c in enumerate(new)}
    old_order = {c.clause_ref: i for i, c in enumerate(old)}
    pairs.sort(
        key=lambda p: (order.get(p[1].clause_ref, 10**6) if p[1] else old_order.get(p[0].clause_ref, 10**6) + 0.5)
    )  # type: ignore[union-attr]

    changes: list[ClauseChange] = []
    for o, n in pairs:
        if o and n:
            ot, nt = normalize_text(o.text), normalize_text(n.text)
            if ot == nt:
                if include_unchanged:
                    changes.append(
                        ClauseChange(ChangeType.UNCHANGED, n.clause_ref, n.title, o.text, n.text, o.page, n.page, 1.0)
                    )
                continue
            changes.append(
                ClauseChange(
                    ChangeType.MODIFIED,
                    n.clause_ref,
                    n.title or o.title,
                    o.text,
                    n.text,
                    o.page,
                    n.page,
                    round(_ratio(ot, nt), 4),
                    inline_diff(ot, nt),
                )
            )
        elif n:
            changes.append(
                ClauseChange(
                    ChangeType.ADDED,
                    n.clause_ref,
                    n.title,
                    None,
                    n.text,
                    None,
                    n.page,
                    0.0,
                    [InlineOp("insert", normalize_text(n.text))],
                )
            )
        elif o:
            changes.append(
                ClauseChange(
                    ChangeType.REMOVED,
                    o.clause_ref,
                    o.title,
                    o.text,
                    None,
                    o.page,
                    None,
                    0.0,
                    [InlineOp("delete", normalize_text(o.text))],
                )
            )
    return DiffResult(changes)
