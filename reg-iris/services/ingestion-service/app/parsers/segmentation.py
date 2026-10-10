"""Split page text into citable clauses.

Heading patterns cover the provided corpus ("Paragraph 3. Title", "Q5: ...") and common
regulatory styles ("Article 26", "Section 4.2", "Rule 10b-5"). Teams can extend HEADING_PATTERNS.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter

from .base import ParsedClause, ParsedPage

HEADING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^\s*(?P<ref>(?:Paragraph|Article|Section|Clause|Rule|Regulation)\s+\d+(?:\.\d+)*[A-Za-z]?)"
        r"\s*[.:\-–]?\s*(?P<title>.*)$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?P<ref>Q\d+)\s*[:.]\s*(?P<title>.*)$"),
]


def _match_heading(line: str) -> tuple[str, str] | None:
    for pattern in HEADING_PATTERNS:
        m = pattern.match(line)
        if m:
            ref = re.sub(r"\s+", " ", m.group("ref")).strip()
            ref = ref[0].upper() + ref[1:]
            return ref, m.group("title").strip() or ""
    return None


def segment_pages(pages: list[ParsedPage]) -> tuple[list[ParsedClause], list[str]]:
    """Return clauses with page spans, plus quality warnings."""
    lines: list[tuple[int, str]] = []  # (page_number, line)
    for page in pages:
        for line in page.text.splitlines():
            lines.append((page.page_number, line.rstrip()))

    starts: list[tuple[int, str, str]] = []  # (line_idx, ref, title)
    for idx, (_, line) in enumerate(lines):
        if heading := _match_heading(line):
            starts.append((idx, *heading))

    warnings: list[str] = []
    if not starts:
        return _fallback_paragraphs(pages), ["No clause headings detected; split on blank lines instead."]

    clauses: list[ParsedClause] = []
    seen: Counter[str] = Counter()
    preamble = " ".join(line for _, line in lines[: starts[0][0]]).strip()
    for n, (idx, ref, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        body_lines = [line for _, line in lines[idx + 1 : end]]
        # Q&A: the question is the title, the answer lines are the body.
        text = " ".join(line.strip() for line in body_lines if line.strip())
        seen[ref] += 1
        if seen[ref] > 1:
            warnings.append(
                f"Clause reference '{ref}' appears {seen[ref]} times — the file may contain more than one document."
            )
            ref = f"{ref} (#{seen[ref]})"
        page_numbers = [p for p, _ in lines[idx:end]] or [lines[idx][0]]
        clauses.append(
            ParsedClause(
                ordinal=n + 1,
                clause_ref=ref,
                title=title or None,
                text=text or title,
                page_start=min(page_numbers),
                page_end=max(page_numbers),
            )
        )
    if len(preamble) > 200:
        warnings.append("Text found before the first clause heading was not attached to any clause.")
    return clauses, warnings


def _fallback_paragraphs(pages: list[ParsedPage]) -> list[ParsedClause]:
    clauses: list[ParsedClause] = []
    for page in pages:
        for block in re.split(r"\n\s*\n", page.text):
            block = " ".join(block.split())
            if len(block) < 20:
                continue
            n = len(clauses) + 1
            clauses.append(ParsedClause(n, f"¶{n}", None, block, page.page_number, page.page_number))
    return clauses


def page_of_offset(page_offsets: list[int], offset: int) -> int:
    return bisect_right(page_offsets, offset)
