"""File storage abstraction. Local volume today; swap for S3/MinIO by implementing FileStorage."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileStorage(Protocol):
    def save(self, data: bytes, sha256: str, extension: str) -> str: ...
    def path(self, key: str) -> Path: ...
    def read(self, key: str) -> bytes: ...


class LocalFileStorage:
    """Content-addressed storage: <root>/<sha[:2]>/<sha>.<ext>. Writing the same file twice is a no-op."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, sha256: str, extension: str) -> str:
        key = f"{sha256[:2]}/{sha256}.{extension}"
        target = self.root / key
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
        return key

    def path(self, key: str) -> Path:
        return self.root / key

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()
