"""Metadata normalisation tests (dates, labels, version families)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.metadata import (
    MetadataError,
    family_key_for,
    import_order,
    infer_day_first,
    normalize_date,
    parse_metadata_csv,
    resolve_family_roots,
)

DATA = Path(__file__).resolve().parents[3] / "data"


def test_supplied_metadata_normalises_dates_and_labels() -> None:
    rows, errors, convention = parse_metadata_csv((DATA / "metadata" / "doc_metadata.csv").read_text())
    assert errors == []
    assert "day-first" in convention
    by_file = {r.file_name: r for r in rows}
    assert by_file["MiFID_II_2023_v1.pdf"].effective_date == date(2023, 7, 1)  # '01-07-23'
    assert by_file["EMIR_2021_v1.pdf"].effective_date == date(2021, 1, 15)  # '15-01-21'
    assert by_file["CFTC_2022.txt"].effective_date == date(2022, 11, 30)
    dodd = by_file["Dodd_Frank_2022.pdf"]
    assert dodd.regulator == "Dodd-Frank"  # non-breaking hyphen folded
    assert any("normalised" in n for n in dodd.notes)


def test_version_families_follow_parent_chain() -> None:
    rows, _, _ = parse_metadata_csv((DATA / "metadata" / "doc_metadata.csv").read_text())
    roots, errors = resolve_family_roots(rows)
    assert errors == []
    assert roots[2] == 1 and roots[4] == 3 and roots[9] == 8
    order = [r.source_id for r in import_order(rows)]
    assert order.index(1) < order.index(2) and order.index(8) < order.index(9)


def test_grandparent_chain_and_unknown_parent() -> None:
    csv = (
        "document_id,file_name,regulator,jurisdiction,effective_date,category,version,upload_timestamp,parent_doc_id\n"
        "1,A_v1.pdf,X,EU,01-01-24,C,v1.0,2024-01-01T00:00:00Z,\n"
        "2,A_v2.pdf,X,EU,01-01-24,C,v2.0,2024-02-01T00:00:00Z,1\n"
        "3,A_v3.pdf,X,EU,01-01-24,C,v3.0,2024-03-01T00:00:00Z,2\n"
        "4,B_v2.pdf,Y,EU,01-01-24,C,v2.0,2024-03-01T00:00:00Z,99\n"
    )
    rows, errors, _ = parse_metadata_csv(csv)
    assert errors == []
    roots, root_errors = resolve_family_roots(rows)
    assert roots[3] == 1
    assert roots[4] == 4
    assert any("parent_doc_id 99 not found" in e for e in root_errors)


def test_date_convention_inference() -> None:
    assert infer_day_first(["01-07-23", "15-01-21"])[0] is True
    assert infer_day_first(["07-31-23"])[0] is False
    with pytest.raises(MetadataError):
        infer_day_first(["15-01-21", "01-31-21"])
    assert normalize_date("2023-07-01") == date(2023, 7, 1)
    assert normalize_date("01/07/2023") == date(2023, 7, 1)
    with pytest.raises(MetadataError):
        normalize_date("31-02-23")


def test_family_key_strips_version_suffix() -> None:
    assert family_key_for("MiFID_II_2023_v2.pdf") == "MiFID_II_2023"
    assert family_key_for("SEC_GUIDANCE_2023_v1.pdf") == "SEC_GUIDANCE_2023"
    assert family_key_for("FCA_Guidance_2023.html") == "FCA_Guidance_2023"


def test_missing_columns_rejected() -> None:
    with pytest.raises(MetadataError):
        parse_metadata_csv("document_id,file_name\n1,a.pdf\n")
