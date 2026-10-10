"""Upload validation and safe storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.storage import UploadRejected, safe_filename, store_upload, validate_upload


def test_safe_filename_strips_path_traversal() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\windows\\evil name.PDF") == "evil_name.pdf"
    with pytest.raises(UploadRejected):
        safe_filename("../..")


def test_validate_upload_accepts_real_pdf(regulations: Path) -> None:
    data = (regulations / "MiFID_II_2023_v1.pdf").read_bytes()
    assert validate_upload("MiFID.pdf", data, 25 * 1024 * 1024) == "pdf"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("report.docx", b"PK\x03\x04", "unsupported_type"),
        ("fake.pdf", b"<html>not a pdf</html>", "invalid_content"),
        ("binary.txt", b"abc\x00\x01\x02", "invalid_content"),
        ("empty.txt", b"", "empty_file"),
        ("plain.html", b"no markup at all", "invalid_content"),
    ],
)
def test_validate_upload_rejects_bad_files(name: str, data: bytes, code: str) -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload(name, data, 1024 * 1024)
    assert exc.value.code == code


def test_validate_upload_enforces_size_limit() -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload("big.txt", b"a" * 2048, 1024)
    assert exc.value.code == "file_too_large"


def test_store_upload_stays_inside_upload_root(tmp_path: Path) -> None:
    path = store_upload(tmp_path, "../../outside", "../x.txt", b"hello")
    assert tmp_path.resolve() in path.parents
    assert path.read_bytes() == b"hello"
