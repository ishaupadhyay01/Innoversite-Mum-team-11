"""Data structures produced by the document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceLine:
    """One physical line of extracted text with its location in the source."""

    text: str
    page: int | None = None  # 1-based PDF page number; None for HTML/TXT
    line_no: int | None = None  # 1-based line number in the source file (TXT only)
    block_break: bool = False  # True when this "line" is a block separator


@dataclass
class Clause:
    """A paragraph or clause: the unit that is indexed and cited."""

    ordinal: int
    heading: str | None
    body: str
    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    anchor: str | None = None  # HTML element id usable as a URL fragment
    part: int | None = None  # set when a very long clause was split into parts

    @property
    def text(self) -> str:
        """Full display text: heading followed by body."""
        if self.heading and self.body:
            return f"{self.heading}\n{self.body}"
        return self.heading or self.body

    @property
    def search_body(self) -> str:
        """Text stored in the full-text content field (body, or heading when there is no body)."""
        return self.body or (self.heading or "")


@dataclass
class ParsedDocument:
    source_type: str  # "pdf" | "html" | "txt"
    title: str | None
    clauses: list[Clause]
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)
    extractor: str = ""

    @property
    def paragraph_count(self) -> int:
        return len(self.clauses)


class ParseError(Exception):
    """Raised when a document cannot be parsed at all (corrupt file, no text)."""
