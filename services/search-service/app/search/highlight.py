"""Safe conversion of Elasticsearch highlight output into text segments.

The highlighter is configured with ``encoder: html``: Elasticsearch escapes the
document text and inserts ``<mark>``/``</mark>``. We split on those tags,
HTML-unescape each piece and return ``[{"text": ..., "highlight": bool}]``.
The frontend renders segments as React text nodes, so no HTML from a
document is ever injected into the page.
"""

from __future__ import annotations

import html
import re

_MARK_RE = re.compile(r"(<mark>|</mark>)")


def to_segments(highlighted: str) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    inside = False
    for piece in _MARK_RE.split(highlighted):
        if piece == "<mark>":
            inside = True
            continue
        if piece == "</mark>":
            inside = False
            continue
        if not piece:
            continue
        text = html.unescape(piece)
        if segments and segments[-1]["highlight"] == inside:
            segments[-1]["text"] = str(segments[-1]["text"]) + text
        else:
            segments.append({"text": text, "highlight": inside})
    return segments


def plain_segments(text: str) -> list[dict[str, object]]:
    return [{"text": text, "highlight": False}] if text else []


def best_highlight(highlight: dict[str, list[str]] | None, fields: list[str], fallback: str) -> list[dict[str, object]]:
    """Pick the highlighted variant with the most marked terms (variants differ by analyzer)."""
    best: str | None = None
    best_marks = 0
    for f in fields:
        for fragment in (highlight or {}).get(f, []):
            marks = fragment.count("<mark>")
            if marks > best_marks:
                best, best_marks = fragment, marks
    if best is None:
        return plain_segments(fallback)
    return to_segments(best)
