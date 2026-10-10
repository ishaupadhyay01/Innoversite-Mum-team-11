"""Deterministic text normalisation used by parsers, indexing and diffing.

The goal is to normalise *presentation* artefacts (non-breaking spaces,
non-breaking hyphens, wrapped lines) without changing meaning. En and em
dashes are kept because they carry meaning in titles such as
"Dodd-Frank Act – 2022".
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Characters that render as a space but break tokenisation or equality checks.
_SPACE_LIKE = {
    " ": " ",  # no-break space
    " ": " ",  # figure space
    " ": " ",  # thin space
    " ": " ",  # narrow no-break space (common in Word-generated PDFs)
    " ": " ",
    " ": " ",
    "\t": " ",
}
# Hyphen variants that mean exactly "-".
_HYPHEN_LIKE = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen (used in the dataset metadata: "Dodd‑Frank")
}
_ZERO_WIDTH = {"​": "", "﻿": "", "­": ""}

_TRANSLATION = str.maketrans({**_SPACE_LIKE, **_HYPHEN_LIKE, **_ZERO_WIDTH})
_MULTI_SPACE = re.compile(r" {2,}")


def normalize_inline(text: str) -> str:
    """Normalise a single line: unify space/hyphen variants and collapse runs of spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(_TRANSLATION)
    return _MULTI_SPACE.sub(" ", text).strip()


def normalize_label(text: str | None) -> str:
    """Normalise a metadata label such as a regulator name ("Dodd‑Frank" -> "Dodd-Frank")."""
    return normalize_inline(text or "")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG_RE.sub("-", normalize_inline(text).lower()).strip("-")
