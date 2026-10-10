"""Document extraction tests on the real supplied files."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import ParseError, parse_document
from app.parsers.html_parser import parse_html
from app.parsers.segmenter import is_heading
from app.parsers.txt_parser import parse_txt


def test_pdf_ingestion_extracts_clauses_with_real_page_numbers(regulations: Path) -> None:
    doc = parse_document(regulations / "MiFID_II_2023_v2.pdf")
    assert doc.source_type == "pdf"
    assert doc.page_count == 2
    headings = [c.heading for c in doc.clauses]
    assert headings[2] == "Paragraph 3. Counterparty LEI Requirement"
    assert len(doc.clauses) == 7
    lei = doc.clauses[2]
    assert lei.page_start == 1 and lei.page_end == 1
    assert "20-character alphanumeric identifier" in lei.body
    new_clause = doc.clauses[6]
    assert new_clause.heading.startswith("Paragraph 7. New Clause")
    assert new_clause.page_start == 2


def test_pdf_clause_spanning_pages_is_not_split(regulations: Path) -> None:
    doc = parse_document(regulations / "EMIR_2021_v2.pdf")
    spanning = [c for c in doc.clauses if c.page_start != c.page_end]
    assert spanning, "expected a clause that continues across a page break"
    clause = spanning[0]
    assert clause.heading == "Paragraph 5. Data Quality Controls"
    assert (clause.page_start, clause.page_end) == (2, 3)
    assert clause.body.startswith("The CFTC will perform automatic validation")


def test_pdf_embedded_title_is_its_own_clause(regulations: Path) -> None:
    doc = parse_document(regulations / "EMIR_2021_v2.pdf")
    p7 = next(c for c in doc.clauses if c.heading and c.heading.startswith("Paragraph 7. New Requirement"))
    assert "Dodd-Frank Act" not in p7.body
    assert any(c.heading == "Dodd-Frank Act – 2022 (Single version)" for c in doc.clauses)


def test_html_extraction_keeps_sections_anchors_and_lists(regulations: Path) -> None:
    doc = parse_html((regulations / "FCA_Guidance_2023.html").read_bytes())
    assert doc.title == "FCA Trade Reporting Guidance – 2023"
    fx = next(c for c in doc.clauses if c.heading == "3. FX-Specific Relaxations")
    assert fx.anchor == "p3"
    assert fx.page_start is None and fx.page_end is None  # no invented page numbers
    timing = next(c for c in doc.clauses if c.heading == "4. Timing of Submission")
    assert "• Derivatives – within 30 minutes of execution." in timing.body
    assert "font-family" not in " ".join(c.text for c in doc.clauses)  # <style> removed


def test_html_ignores_scripts() -> None:
    html = b"<html><body><h2 id='s'>Scope</h2><p>Visible text.</p><script>alert('x')</script></body></html>"
    doc = parse_html(html)
    assert doc.clauses[0].body == "Visible text."
    assert "alert" not in doc.clauses[0].text


def test_txt_extraction_preserves_paragraphs_and_line_numbers(regulations: Path) -> None:
    doc = parse_txt((regulations / "CFTC_2022.txt").read_bytes())
    assert doc.title == "CFTC (2022) – Commodity Futures Reporting FAQ"
    q3 = next(c for c in doc.clauses if c.heading and c.heading.startswith("Q3:"))
    assert q3.body.startswith("A3: No – the price field must be a non-negative numeric value.")
    assert (q3.line_start, q3.line_end) == (9, 10)
    assert q3.page_start is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Paragraph 3. Counterparty LEI Requirement", True),
        ("Q10: How are amendments handled?", True),
        ("2. Mandatory Reporting Fields", True),
        ("Article 25", True),
        ("All investment firms shall report, for each trade, the following fields.", False),
        ("2017/2402 regulation text continues here", False),
    ],
)
def test_heading_detection(line: str, expected: bool) -> None:
    assert is_heading(line) is expected


def test_corrupt_pdf_raises_parse_error(tmp_path: Path) -> None:
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    with pytest.raises(ParseError):
        parse_document(bad)


def test_empty_text_document_raises(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        parse_txt(b"   \n\n  ")
