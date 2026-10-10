"""Highlight sanitisation and citation construction."""

from __future__ import annotations

from app.search.highlight import best_highlight, to_segments
from app.search.service import citation_for, location_label


def test_segments_split_marks_and_unescape_text() -> None:
    segs = to_segments("The <mark>Counterparty</mark> &lt;script&gt;x&lt;/script&gt; <mark>LEI</mark>")
    assert segs == [
        {"text": "The ", "highlight": False},
        {"text": "Counterparty", "highlight": True},
        {"text": " <script>x</script> ", "highlight": False},  # plain text, rendered as text nodes
        {"text": "LEI", "highlight": True},
    ]


def test_best_highlight_prefers_most_marked_variant_and_falls_back() -> None:
    hl = {"content": ["<mark>LEI</mark> rules"], "content.exact": ["<mark>LEI</mark> <mark>rules</mark>"]}
    segs = best_highlight(hl, ["content", "content.exact"], "fallback")
    assert sum(1 for s in segs if s["highlight"]) == 2
    assert best_highlight(None, ["content"], "plain text") == [{"text": "plain text", "highlight": False}]


BASE = {
    "paragraph_id": "v2-p0003",
    "document_id": "1",
    "document_version_id": "2",
    "document_name": "MiFID_II_2023_v2.pdf",
    "document_title": "MiFID II 2023",
    "regulator": "MiFID II",
    "version": "v2.0",
    "section_heading": "Paragraph 3. Counterparty LEI Requirement",
}


def test_pdf_citation_links_to_page() -> None:
    c = citation_for({**BASE, "source_type": "pdf", "page_start": 1, "page_end": 1})
    assert c.location_label == "Page 1"
    assert c.source_url == "/api/documents/1/source?version_id=2#page=1"
    assert c.viewer_url == "/viewer/2?paragraph=v2-p0003"


def test_html_citation_uses_anchor_and_never_invents_pages() -> None:
    c = citation_for({**BASE, "source_type": "html", "page_start": None, "anchor": "p3"})
    assert c.page_start is None
    assert c.location_label == "Section #p3"
    assert c.source_url.endswith("#p3")


def test_txt_citation_uses_line_numbers() -> None:
    assert location_label({"source_type": "txt", "line_start": 9, "line_end": 10}) == "Lines 9–10"
    assert location_label({"source_type": "pdf", "page_start": 2, "page_end": 3}) == "Pages 2–3"
