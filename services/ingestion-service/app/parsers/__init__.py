"""Document parsers for PDF, HTML and TXT regulatory sources."""

from __future__ import annotations

from pathlib import Path

from .html_parser import parse_html
from .pdf_parser import parse_pdf
from .structures import Clause, ParsedDocument, ParseError, SourceLine
from .txt_parser import parse_txt

SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".txt": "txt"}


def source_type_for(filename: str) -> str | None:
    return SUPPORTED_EXTENSIONS.get(Path(filename).suffix.lower())


def parse_document(path: Path, source_type: str | None = None) -> ParsedDocument:
    """Parse a stored file into clauses. Raises ParseError for unreadable documents."""
    source_type = source_type or source_type_for(path.name)
    if source_type == "pdf":
        return parse_pdf(path)
    raw = path.read_bytes()
    if source_type == "html":
        return parse_html(raw)
    if source_type == "txt":
        return parse_txt(raw)
    raise ParseError(f"Unsupported document type for {path.name!r}")


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "Clause",
    "ParseError",
    "ParsedDocument",
    "SourceLine",
    "parse_document",
    "source_type_for",
]
