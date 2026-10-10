"""Plain-text extraction preserving logical paragraphs and source line numbers.

Blank lines separate paragraphs. Section headings (``Q3: ...``,
``Paragraph 2. ...``, underlined titles) are detected by the shared
segmenter. TXT files have no pages; each clause records the source line
range so the citation can point to ``lines 12–13``.
"""

from __future__ import annotations

from .segmenter import segment
from .structures import ParsedDocument, ParseError, SourceLine


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_txt(raw: bytes) -> ParsedDocument:
    text = decode_text(raw).replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise ParseError("File contains binary data and is not a plain-text document")
    lines: list[SourceLine] = []
    for idx, line in enumerate(text.split("\n"), start=1):
        if line.strip():
            lines.append(SourceLine(line, line_no=idx))
        else:
            lines.append(SourceLine("", line_no=idx, block_break=True))
    clauses = segment(lines)
    if not clauses:
        raise ParseError("Text document is empty")
    title = clauses[0].heading if clauses[0].heading and not clauses[0].body else None
    return ParsedDocument(source_type="txt", title=title, clauses=clauses, extractor="text")
