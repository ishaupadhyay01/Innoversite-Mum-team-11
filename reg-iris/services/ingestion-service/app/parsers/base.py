from __future__ import annotations

from dataclasses import dataclass, field


class UnsupportedFormatError(ValueError):
    pass


@dataclass
class ParsedPage:
    page_number: int
    text: str


@dataclass
class ParsedClause:
    ordinal: int
    clause_ref: str
    title: str | None
    text: str
    page_start: int
    page_end: int
    anchor: str | None = None


@dataclass
class ParsedDocument:
    format: str
    title: str | None
    pages: list[ParsedPage]
    clauses: list[ParsedClause]
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)
