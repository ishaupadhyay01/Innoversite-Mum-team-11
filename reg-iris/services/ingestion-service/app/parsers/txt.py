from __future__ import annotations

from .base import ParsedDocument, ParsedPage
from .segmentation import segment_pages


def parse_txt(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8-sig", errors="replace")
    # Form feed (\f) is the conventional page break in plain-text exports.
    pages = [ParsedPage(i + 1, chunk) for i, chunk in enumerate(text.split("\f"))]
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
    clauses, warnings = segment_pages(pages)
    return ParsedDocument("txt", first_line, pages, clauses, warnings)
