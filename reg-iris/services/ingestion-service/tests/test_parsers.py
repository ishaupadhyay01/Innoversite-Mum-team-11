import pytest

from app.parsers import UnsupportedFormatError, detect_format, parse_document
from tests.conftest import sample


def test_pdf_is_split_into_paragraph_clauses_with_pages():
    doc = parse_document("pdf", sample("MiFID_II_2023_v2.pdf"))
    refs = [c.clause_ref for c in doc.clauses]
    assert refs == [f"Paragraph {i}" for i in range(1, 8)]
    lei = doc.clauses[2]
    assert lei.title == "Counterparty LEI Requirement"
    assert "20-character" in lei.text
    assert doc.clauses[-1].page_start == 2


def test_html_sections_keep_anchor_for_deep_links():
    doc = parse_document("html", sample("FCA_Guidance_2023.html"))
    fx = next(c for c in doc.clauses if "FX" in (c.title or ""))
    assert fx.anchor == "p3" and fx.clause_ref == "Section 3"


def test_txt_faq_is_split_on_questions():
    doc = parse_document("txt", sample("CFTC_2022.txt"))
    assert [c.clause_ref for c in doc.clauses][:3] == ["Q1", "Q2", "Q3"]


def test_concatenated_pdf_raises_quality_warning():
    doc = parse_document("pdf", sample("EMIR_2021_v2.pdf"))
    assert any("more than one document" in w for w in doc.warnings)


@pytest.mark.parametrize("name,data", [("fake.pdf", b"hello"), ("evil.exe", b"MZ"), ("page.html", b"plain text")])
def test_detect_format_rejects_mismatched_content(name, data):
    with pytest.raises(UnsupportedFormatError):
        detect_format(name, data)
