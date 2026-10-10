import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ClauseChange } from "@/api/types";
import { DiffView } from "./DiffView";

const change = (c: Partial<ClauseChange>): ClauseChange => ({
  change: "MODIFIED", clause_ref: "Paragraph 3", title: "LEI", old_text: "a", new_text: "b",
  old_page: 1, new_page: 1, similarity: 0.9, inline: [], ...c,
});

describe("DiffView", () => {
  it("renders added, removed and modified clauses with inline insertions/deletions", () => {
    render(
      <DiffView
        changes={[
          change({ inline: [{ op: "equal", text: "must be" }, { op: "delete", text: "positive" }, { op: "insert", text: "non-negative" }] }),
          change({ change: "ADDED", clause_ref: "Paragraph 7", old_page: null, inline: [{ op: "insert", text: "Execution venue" }] }),
          change({ change: "REMOVED", clause_ref: "Paragraph 9", new_page: null, inline: [{ op: "delete", text: "Old text" }] }),
        ]}
      />,
    );
    expect(screen.getByText("MODIFIED")).toBeInTheDocument();
    expect(screen.getByText("ADDED")).toBeInTheDocument();
    expect(screen.getByText("REMOVED")).toBeInTheDocument();
    expect(screen.getByText(/non-negative/)).toHaveClass("text-pass");
    expect(screen.getByText(/positive/, { selector: ".line-through" })).toBeInTheDocument();
  });

  it("says so when there are no differences", () => {
    render(<DiffView changes={[]} />);
    expect(screen.getByText("No differences.")).toBeInTheDocument();
  });
});
