"""PDF extraction: page-by-page text with real page numbers.

PyMuPDF (``fitz``) is the primary extractor. ``pypdf`` is used only as a
fallback when PyMuPDF is not importable (for example in a minimal test
environment); the extractor actually used is recorded on the result.
"""

from __future__ import annotations

from pathlib import Path

from .segmenter import segment
from .structures import ParsedDocument, ParseError, SourceLine


def _extract_pymupdf(path: Path) -> tuple[list[SourceLine], int, list[int], str | None]:
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception as exc:  # fitz raises several exception types for corrupt files
        raise ParseError(f"PDF could not be opened: {exc}") from exc
    if doc.needs_pass:
        raise ParseError("PDF is password-protected; encrypted documents are not supported")

    lines: list[SourceLine] = []
    empty_pages: list[int] = []
    title = (doc.metadata or {}).get("title") or None
    for page_no, page in enumerate(doc, start=1):
        blocks = page.get_text("blocks", sort=True)
        page_has_text = False
        for block in blocks:
            # block = (x0, y0, x1, y1, text, block_no, block_type); type 0 is text
            if len(block) >= 7 and block[6] != 0:
                continue
            text = block[4] or ""
            if not text.strip():
                continue
            page_has_text = True
            for raw in text.splitlines():
                lines.append(SourceLine(raw, page=page_no))
            lines.append(SourceLine("", page=page_no, block_break=True))
        if not page_has_text:
            empty_pages.append(page_no)
    page_count = doc.page_count
    doc.close()
    return lines, page_count, empty_pages, title


def _extract_pypdf(path: Path) -> tuple[list[SourceLine], int, list[int], str | None]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ParseError(f"PDF could not be opened: {exc}") from exc
    if reader.is_encrypted:
        raise ParseError("PDF is password-protected; encrypted documents are not supported")
    lines: list[SourceLine] = []
    empty_pages: list[int] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            empty_pages.append(page_no)
            continue
        for raw in text.splitlines():
            if raw.strip():
                lines.append(SourceLine(raw, page=page_no))
            else:
                lines.append(SourceLine("", page=page_no, block_break=True))
        lines.append(SourceLine("", page=page_no, block_break=True))
    title = None
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title)
    return lines, len(reader.pages), empty_pages, title


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        lines, page_count, empty_pages, title = _extract_pymupdf(path)
        extractor = "pymupdf"
    except ImportError:
        lines, page_count, empty_pages, title = _extract_pypdf(path)
        extractor = "pypdf-fallback"

    warnings: list[str] = []
    if empty_pages:
        warnings.append(
            f"No extractable text on page(s) {', '.join(map(str, empty_pages))} (possibly scanned images; OCR is not performed)"
        )
    clauses = segment(lines)
    if not clauses:
        raise ParseError("No extractable text found in PDF (scanned documents require OCR, which is not supported)")
    return ParsedDocument(
        source_type="pdf",
        title=title,
        clauses=clauses,
        page_count=page_count,
        warnings=warnings,
        empty_pages=empty_pages,
        extractor=extractor,
    )
