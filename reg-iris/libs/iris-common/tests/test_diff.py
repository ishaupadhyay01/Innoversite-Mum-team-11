from iris_common.diff import ChangeType, ClauseInput, diff_clauses


def test_diff_detects_added_removed_modified():
    old = [
        ClauseInput("P1", "Scope of the rule."),
        ClauseInput("P2", "Price must be positive."),
        ClauseInput("P3", "Retention is five years."),
    ]
    new = [
        ClauseInput("P1", "Scope of the rule."),
        ClauseInput("P2", "Price must be non-negative."),
        ClauseInput("P4", "Reports are due within 15 minutes."),
    ]
    result = diff_clauses(old, new)
    kinds = {c.clause_ref: c.change for c in result.changes}
    assert kinds == {
        "P1": ChangeType.UNCHANGED,
        "P2": ChangeType.MODIFIED,
        "P4": ChangeType.ADDED,
        "P3": ChangeType.REMOVED,
    }
    mod = next(c for c in result.changes if c.change is ChangeType.MODIFIED)
    assert any(op.op == "insert" and "non-negative" in op.text for op in mod.inline)
    assert result.summary["MODIFIED"] == 1


def test_diff_pairs_renumbered_clause():
    old = [ClauseInput("Paragraph 5", "All reports must be retained for a minimum of five years by the firm.")]
    new = [ClauseInput("Paragraph 6", "All reports must be retained for a minimum of seven years by the firm.")]
    result = diff_clauses(old, new)
    assert [c.change for c in result.changes] == [ChangeType.MODIFIED]
