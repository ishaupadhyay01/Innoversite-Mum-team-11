from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .base import ParsedClause, ParsedDocument, ParsedPage
from .segmentation import segment_pages

_SECTION_NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+(.*)$")


def parse_html(data: bytes) -> ParsedDocument:
    soup = BeautifulSoup(data, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else None) or (
        soup.h1.get_text(" ", strip=True) if soup.h1 else None
    )
    body = soup.body or soup
    full_text = body.get_text("\n", strip=True)
    pages = [ParsedPage(1, full_text)]  # HTML has no pages; citations use the anchor instead.

    headings = body.find_all(["h2", "h3"])
    if not headings:
        clauses, warnings = segment_pages(pages)
        return ParsedDocument("html", title, pages, clauses, warnings)

    clauses: list[ParsedClause] = []
    for n, heading in enumerate(headings, start=1):
        heading_text = heading.get_text(" ", strip=True)
        m = _SECTION_NUM.match(heading_text)
        ref = f"Section {m.group(1)}" if m else f"Section {n}"
        section_title = m.group(2) if m else heading_text
        parts: list[str] = []
        anchor = heading.get("id")
        for sib in heading.next_siblings:
            if isinstance(sib, Tag):
                if sib.name in ("h1", "h2", "h3"):
                    break
                anchor = anchor or sib.get("id")
                parts.append(sib.get_text(" ", strip=True))
            else:  # bare text nodes (e.g. text after a <ul> that closed a <p>)
                parts.append(str(sib).strip())
        clauses.append(
            ParsedClause(
                n,
                ref,
                section_title,
                " ".join(p for p in parts if p) or section_title,
                1,
                1,
                anchor=str(anchor) if anchor else None,
            )
        )
    return ParsedDocument("html", title, pages, clauses, [])
