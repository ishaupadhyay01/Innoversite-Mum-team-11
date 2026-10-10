from __future__ import annotations

from collections.abc import Callable

from .base import ParsedDocument, UnsupportedFormatError
from .html import parse_html
from .pdf import parse_pdf
from .txt import parse_txt

PARSERS: dict[str, Callable[[bytes], ParsedDocument]] = {"pdf": parse_pdf, "html": parse_html, "txt": parse_txt}
MIME_TYPES = {"pdf": "application/pdf", "html": "text/html", "txt": "text/plain"}


def detect_format(filename: str, data: bytes) -> str:
    """Validate by extension AND content signature (never trust the extension alone)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    head = data[:2048].lstrip().lower()
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise UnsupportedFormatError("File has a .pdf extension but is not a PDF")
        return "pdf"
    if ext in ("html", "htm"):
        if not (head.startswith(b"<!doctype html") or b"<html" in head):
            raise UnsupportedFormatError("File has an .html extension but does not look like HTML")
        return "html"
    if ext == "txt":
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedFormatError("Text file is not valid UTF-8") from exc
        return "txt"
    raise UnsupportedFormatError(f"Unsupported file type '.{ext}'. Allowed: PDF, HTML, TXT")


def parse_document(fmt: str, data: bytes) -> ParsedDocument:
    try:
        return PARSERS[fmt](data)
    except KeyError as exc:
        raise UnsupportedFormatError(fmt) from exc
