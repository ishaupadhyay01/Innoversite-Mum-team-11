"""HTML extraction: headings, paragraphs and lists with section anchors.

Scripts, styles and other non-content markup are discarded. Each heading
(h1–h6) starts a section; the text that follows it until the next heading is
the section body. The first ``id`` found inside a section becomes the
clause anchor, so citations can link to ``file.html#p3``. HTML has no page
numbers, so ``page_start``/``page_end`` are always ``None``.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from iris_shared.text import normalize_inline

from .structures import Clause, ParsedDocument, ParseError

_REMOVE = {"script", "style", "noscript", "template", "iframe", "svg", "canvas", "object", "embed", "head"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCKS = {"p", "li", "blockquote", "pre", "td", "th", "dd", "dt", "figcaption", "address", "caption"}
_BREAKING = _BLOCKS | {"ul", "ol", "div", "br", "tr", "table", "section", "article", "dl"}
_WS = re.compile(r"[ \t\r\f\v]+")


def _block_text(el: Tag) -> str:
    """Text of an element, with list items as bullet lines and block children on new lines."""
    parts: list[str] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in {"Comment", "Doctype", "CData", "ProcessingInstruction"}:
                    continue
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in _REMOVE:
                    continue
                if child.name == "li":
                    parts.append("\n• ")
                    walk(child)
                    parts.append("\n")
                elif child.name in _BREAKING:
                    parts.append("\n")
                    walk(child)
                    parts.append("\n")
                else:
                    walk(child)

    walk(el)
    text = "".join(parts)
    lines = [normalize_inline(_WS.sub(" ", ln)) for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _first_id(el: Tag) -> str | None:
    if el.get("id"):
        return str(el["id"])
    found = el.find(attrs={"id": True})
    return str(found["id"]) if found else None


def parse_html(raw: bytes) -> ParsedDocument:
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        html = raw.decode("latin-1")
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = normalize_inline(title_tag.get_text()) if title_tag else None
    for tag in soup.find_all(list(_REMOVE)):
        tag.decompose()
    root = soup.body or soup

    # (heading_text, heading_anchor, [(block_text, anchor)])
    sections: list[tuple[str | None, str | None, list[tuple[str, str | None]]]] = []

    def add_block(text: str, anchor: str | None) -> None:
        if not text:
            return
        if not sections:
            sections.append((None, None, []))
        sections[-1][2].append((text, anchor))

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ != "NavigableString":
                    continue
                text = normalize_inline(_WS.sub(" ", str(child)))
                add_block(text, None)
            elif isinstance(child, Tag):
                if child.name in _HEADINGS:
                    sections.append((normalize_inline(child.get_text(" ")), child.get("id"), []))
                elif child.name in _BLOCKS:
                    add_block(_block_text(child), _first_id(child))
                else:
                    walk(child)

    walk(root)

    clauses: list[Clause] = []
    for heading, heading_anchor, blocks in sections:
        body = "\n".join(text for text, _ in blocks).strip()
        anchor = heading_anchor or next((a for _, a in blocks if a), None)
        if not (heading or body):
            continue
        clauses.append(
            Clause(
                ordinal=len(clauses) + 1,
                heading=heading or None,
                body=body,
                anchor=str(anchor) if anchor else None,
            )
        )
    if not clauses:
        raise ParseError("No readable text content found in HTML document")
    if not title:
        first_h1 = next((c.heading for c in clauses if c.heading), None)
        title = first_h1
    return ParsedDocument(source_type="html", title=title, clauses=clauses, extractor="beautifulsoup")
