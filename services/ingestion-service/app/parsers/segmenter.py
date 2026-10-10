"""Clause-aware segmentation shared by the PDF and TXT parsers.

Input: a flat list of :class:`SourceLine` objects (with page / line numbers and
block separators). Output: :class:`Clause` objects.

Rules (deterministic, documented in ARCHITECTURE.md):

1. Lines are grouped into *units* separated by blank lines / block breaks.
2. A line matching ``HEADING_RE`` (``Paragraph 3. ...``, ``Article 25``,
   ``Q4: ...``, ``2. Mandatory Reporting Fields``) always starts a new clause.
3. A short "title-like" line (e.g. an embedded document title) that sits
   between sentences also starts a new clause, so it is not glued onto the
   end of the previous clause.
4. Body units that follow a heading are merged into that clause — including
   across page boundaries — so a clause is never split mid-way. The clause
   records ``page_start``/``page_end``.
5. Very long clauses are split at unit boundaries into numbered parts that
   share the heading.
6. Pure page furniture ("Page 3 of 6", lone page numbers) is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from iris_shared.text import normalize_inline

from .structures import Clause, SourceLine

HEADING_RE = re.compile(
    r"""^(
        (paragraph|section|article|clause|part|chapter|annex|schedule|rule)\s+
            [0-9IVXLC]+[A-Za-z]?(\.\d+)*(\s*[.:)\-–]\s*.{0,160}|\s+.{1,160})?
      | Q\d{1,3}\s*[:.)]\s+.+
      | \d{1,2}(\.\d{1,2}){0,3}[.)]?\s+[A-Z][^.?!]{1,90}
    )$""",
    re.IGNORECASE | re.VERBOSE,
)
_UNDERLINE_RE = re.compile(r"^[-=_~*]{3,}$")
_PAGE_FURNITURE_RE = re.compile(r"^(page\s+\d+(\s+of\s+\d+)?|\d{1,4}|-\s*\d{1,4}\s*-)$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^([*•·▪◦‣-]|\(?[a-z0-9]{1,3}[.)])\s+", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.:;!?)”\"']$")
_TITLE_FORBIDDEN_END_RE = re.compile(r"[.:;,!?]$")

MAX_CLAUSE_CHARS = 2400
TITLE_MAX_CHARS = 70


def is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 180:
        return False
    return bool(HEADING_RE.match(line))


def _is_title_like(line: str, prev_line: str | None, next_line: str | None) -> bool:
    """A short standalone line that reads as a title, not as a wrapped sentence fragment."""
    s = line.strip()
    if not s or len(s) > TITLE_MAX_CHARS or _BULLET_RE.match(s):
        return False
    if _TITLE_FORBIDDEN_END_RE.search(s) and not s.lower().endswith((".pdf", ".html", ".txt")):
        return False
    prev_ok = prev_line is None or bool(_SENTENCE_END_RE.search(prev_line.strip()))
    if not prev_ok:
        return False
    if next_line is None:
        return True
    nxt = next_line.strip()
    return bool(nxt) and (nxt[0].isupper() or nxt[0].isdigit() or is_heading(nxt))


@dataclass
class _Unit:
    lines: list[SourceLine] = field(default_factory=list)
    forced_heading: bool = False  # unit is a single title-like line

    @property
    def first(self) -> SourceLine:
        return self.lines[0]


def _join_lines(lines: list[str]) -> str:
    """Join wrapped lines into prose; keep bullet items on their own lines."""
    out: list[str] = []
    for raw in lines:
        line = normalize_inline(raw)
        if not line:
            continue
        if not out:
            out.append(line)
        elif _BULLET_RE.match(line):
            out.append("\n" + line)
        elif out[-1].endswith("-") and not out[-1].endswith(" -") and line[:1].islower():
            out[-1] = out[-1] + line  # "over-the-\ncounter" -> "over-the-counter"
        else:
            out[-1] = out[-1] + " " + line
    return "".join(out).replace(" \n", "\n").strip()


def _build_units(lines: list[SourceLine]) -> list[_Unit]:
    # Normalise, drop page furniture and turn underline decorations into block breaks.
    cleaned: list[SourceLine] = []
    for ln in lines:
        text = normalize_inline(ln.text)
        if ln.block_break or not text or _UNDERLINE_RE.match(text):
            cleaned.append(SourceLine("", ln.page, ln.line_no, block_break=True))
            continue
        if _PAGE_FURNITURE_RE.match(text):
            continue
        cleaned.append(SourceLine(text, ln.page, ln.line_no))

    units: list[_Unit] = []
    current = _Unit()

    def flush() -> None:
        nonlocal current
        if current.lines:
            units.append(current)
        current = _Unit()

    for idx, ln in enumerate(cleaned):
        if ln.block_break:
            flush()
            continue
        if is_heading(ln.text):
            flush()
            current.lines.append(ln)
            continue
        prev_text = current.lines[-1].text if current.lines else None
        if _is_title_like(ln.text, prev_text, _next_nonblank(cleaned, idx)):
            flush()
            units.append(_Unit([ln], forced_heading=True))
            continue
        current.lines.append(ln)
    flush()
    return units


def _next_nonblank(lines: list[SourceLine], idx: int) -> str | None:
    for j in range(idx + 1, len(lines)):
        if not lines[j].block_break:
            return lines[j].text
    return None


def _locate(lines: list[SourceLine]) -> tuple[int | None, int | None, int | None, int | None]:
    pages = [ln.page for ln in lines if ln.page is not None]
    nums = [ln.line_no for ln in lines if ln.line_no is not None]
    return (
        min(pages) if pages else None,
        max(pages) if pages else None,
        min(nums) if nums else None,
        max(nums) if nums else None,
    )


def segment(lines: list[SourceLine]) -> list[Clause]:
    """Segment extracted lines into clauses (see module docstring for the rules)."""
    units = _build_units(lines)

    drafts: list[tuple[str | None, list[list[SourceLine]]]] = []
    for unit in units:
        first = unit.first.text
        if unit.forced_heading:
            drafts.append((first, []))
        elif is_heading(first):
            heading = first
            rest = unit.lines[1:]
            drafts.append((heading, [rest] if rest else []))
        else:
            if (drafts and drafts[-1][0] is not None) or (drafts and drafts[-1][0] is None):
                drafts[-1][1].append(unit.lines)
            else:
                drafts.append((None, [unit.lines]))

    clauses: list[Clause] = []
    for heading, body_units in drafts:
        heading_norm = normalize_inline(heading) if heading else None
        heading_line = _find_heading_line(units, heading)
        parts = _split_long(body_units)
        if not parts:
            parts = [[]]
        for part_idx, part_units in enumerate(parts):
            all_lines = [ln for u in part_units for ln in u]
            locate_lines = list(all_lines)
            if part_idx == 0 and heading_line is not None:
                locate_lines.insert(0, heading_line)
            page_start, page_end, line_start, line_end = _locate(locate_lines)
            body = "\n".join(_join_lines([ln.text for ln in u]) for u in part_units if u).strip()
            clauses.append(
                Clause(
                    ordinal=len(clauses) + 1,
                    heading=heading_norm,
                    body=body,
                    page_start=page_start,
                    page_end=page_end,
                    line_start=line_start,
                    line_end=line_end,
                    part=(part_idx + 1) if len(parts) > 1 else None,
                )
            )
    return [c for c in clauses if c.text.strip()]


def _find_heading_line(units: list[_Unit], heading: str | None) -> SourceLine | None:
    if heading is None:
        return None
    for unit in units:
        if unit.first.text == heading:
            return unit.first
    return None


def _split_long(body_units: list[list[SourceLine]]) -> list[list[list[SourceLine]]]:
    if not body_units:
        return []
    parts: list[list[list[SourceLine]]] = [[]]
    size = 0
    for unit in body_units:
        unit_len = sum(len(ln.text) + 1 for ln in unit)
        if parts[-1] and size + unit_len > MAX_CLAUSE_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(unit)
        size += unit_len
    return parts
