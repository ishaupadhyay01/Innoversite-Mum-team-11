from __future__ import annotations

import pymupdf

from .base import ParsedDocument, ParsedPage
from .segmentation import segment_pages


def parse_pdf(data: bytes) -> ParsedDocument:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pages = [ParsedPage(i + 1, page.get_text("text")) for i, page in enumerate(doc)]
        title = (doc.metadata or {}).get("title") or None
    clauses, warnings = segment_pages(pages)
    if not any(p.text.strip() for p in pages):
        warnings.append("PDF has no extractable text (scanned?). OCR is not enabled.")
    return ParsedDocument("pdf", title, pages, clauses, warnings)
