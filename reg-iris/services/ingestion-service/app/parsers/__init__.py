"""Document parsers: bytes → ParsedDocument (pages + citable clauses).

Add a format by writing a parser function and registering it in ``registry.PARSERS``.
"""

from .base import ParsedClause, ParsedDocument, ParsedPage, UnsupportedFormatError
from .registry import detect_format, parse_document

__all__ = ["ParsedClause", "ParsedDocument", "ParsedPage", "UnsupportedFormatError", "detect_format", "parse_document"]
