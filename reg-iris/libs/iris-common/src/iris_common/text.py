"""Text utilities: hashing, normalisation, shingling and similarity."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")
# Unicode dashes/hyphens (e.g. U+2011 in "Dodd‑Frank" from doc_metadata.csv) → ASCII "-"
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_DASHES)
    return _WS.sub(" ", text).strip()


def canonical_regulator(name: str | None) -> str | None:
    """'Dodd‑Frank' / 'dodd-frank ' / 'DODD FRANK' → 'DODD-FRANK'. Used for joins across services."""
    if not name:
        return None
    return re.sub(r"[\s_]+", "-", normalize_text(name)).upper()


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize_text(text).lower())


def shingles(text: str, k: int = 5) -> set[str]:
    toks = tokens(text)
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def minhash_signature(items: set[str], num_perm: int = 64) -> list[int]:
    """Small dependency-free MinHash so near-duplicate checks don't need the full text."""
    if not items:
        return [0] * num_perm
    sig = []
    for seed in range(num_perm):
        salt = seed.to_bytes(2, "big")
        sig.append(
            min(int.from_bytes(hashlib.blake2b(salt + s.encode(), digest_size=8).digest(), "big") for s in items)
        )
    return sig


def minhash_similarity(a: list[int], b: list[int]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)
