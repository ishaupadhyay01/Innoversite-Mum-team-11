"""Upload validation and safe file storage."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..parsers import SUPPORTED_EXTENSIONS

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_filename(name: str) -> str:
    """Strip any path components and unsafe characters: '../../etc/passwd' -> 'passwd'."""
    base = Path(name.replace("\\", "/")).name
    base = _SAFE_CHARS.sub("_", base).strip("._")
    if not base:
        raise UploadRejected("invalid_filename", "File name is empty after removing unsafe characters")
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    stem = stem[:120] or "document"
    return f"{stem}.{ext.lower()}" if ext else stem


def validate_upload(file_name: str, data: bytes, max_bytes: int) -> str:
    """Validate type, size and content. Returns the source type ('pdf'|'html'|'txt')."""
    ext = Path(file_name).suffix.lower()
    source_type = SUPPORTED_EXTENSIONS.get(ext)
    if source_type is None:
        raise UploadRejected("unsupported_type", f"Unsupported file type {ext or '(none)'}; allowed: PDF, HTML, TXT")
    if not data:
        raise UploadRejected("empty_file", "Uploaded file is empty")
    if len(data) > max_bytes:
        raise UploadRejected("file_too_large", f"File exceeds the {max_bytes // (1024 * 1024)} MB limit")
    if source_type == "pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise UploadRejected("invalid_content", "File has a .pdf extension but is not a PDF document")
    else:
        if b"\x00" in data[:8192]:
            raise UploadRejected("invalid_content", "File appears to be binary, not text/HTML")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                data.decode("latin-1")
            except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 decodes any byte
                raise UploadRejected("invalid_content", "File is not valid text") from exc
        if source_type == "html" and b"<" not in data[:65536]:
            raise UploadRejected("invalid_content", "File has an .html extension but contains no HTML markup")
    return source_type


def store_upload(upload_root: Path, document_key: str, file_name: str, data: bytes) -> Path:
    """Write the file under upload_root/<document_key>/<uuid>_<safe name>; never outside upload_root."""
    root = upload_root.resolve()
    folder = (root / _SAFE_CHARS.sub("_", document_key)).resolve()
    target = (folder / f"{uuid.uuid4().hex[:12]}_{safe_filename(file_name)}").resolve()
    if root not in target.parents:
        raise UploadRejected("invalid_path", "Resolved storage path escapes the upload directory")
    folder.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def is_within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == r.resolve() or r.resolve() in resolved.parents for r in roots)
