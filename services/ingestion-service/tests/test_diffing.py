"""Deterministic version comparison tests."""

from __future__ import annotations

from pathlib import Path

from app.parsers import parse_document
from app.services.diffing import ClauseRef, compare, inline_diff


def refs(path: Path) -> list[ClauseRef]:
    return [
        ClauseRef(c.ordinal, c.heading, c.body, c.page_start, c.page_end, c.line_start, c.line_end, c.anchor)
        for c in parse_document(path).clauses
    ]


def test_mifid_v1_to_v2_detects_exactly_one_added_clause(regulations: Path) -> None:
    result = compare(refs(regulations / "MiFID_II_2023_v1.pdf"), refs(regulations / "MiFID_II_2023_v2.pdf"))
    assert result.stats["added"] == 1
    assert result.stats["removed"] == 0 and result.stats["modified"] == 0
    assert result.stats["unchanged"] == 6
    assert result.change_types == ["Added Clause"]
    added = next(r for r in result.rows if r.change == "added")
    assert added.new.heading.startswith("Paragraph 7. New Clause – Execution Venue Disclosure")
    assert added.new.page_start == 2
    assert "Execution Venue Disclosure" in result.summary and "(p. 2)" in result.summary


def test_reverse_comparison_reports_removed_clause(regulations: Path) -> None:
    result = compare(refs(regulations / "SEC_GUIDANCE_2023_v2.pdf"), refs(regulations / "SEC_GUIDANCE_2023_v1.pdf"))
    assert result.stats["removed"] == 1
    assert result.change_types == ["Removed Clause"]


def test_modified_clause_gets_inline_diff() -> None:
    old = [ClauseRef(1, "Paragraph 1. Timing", "Report within one business day of execution.", 1, 1)]
    new = [ClauseRef(1, "Paragraph 1. Timing", "Report within 15 minutes of execution.", 1, 1)]
    result = compare(old, new)
    assert result.stats["modified"] == 1
    row = result.rows[0]
    ops = {seg["op"] for seg in row.inline}
    assert {"equal", "delete", "insert"} <= ops
    assert "Modified Clause" in result.change_types


def test_identical_documents_have_no_changes(regulations: Path) -> None:
    a = refs(regulations / "Dodd_Frank_2022.pdf")
    result = compare(a, a)
    assert result.change_types == []
    assert result.summary.startswith("No textual differences")


def test_inline_diff_is_word_level() -> None:
    segs = inline_diff("price must be positive", "price must be non-negative")
    assert segs[0] == {"op": "equal", "text": "price must be "}
