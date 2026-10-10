from iris_common.text import canonical_regulator, jaccard, minhash_signature, minhash_similarity, shingles


def test_canonical_regulator_handles_unicode_hyphen():
    assert canonical_regulator("Dodd‑Frank") == canonical_regulator("dodd-frank") == "DODD-FRANK"
    assert canonical_regulator("MiFID II") == "MIFID-II"


def test_minhash_tracks_jaccard():
    a = shingles("the counterparty LEI must be a valid twenty character identifier issued by an LOU " * 3)
    b = shingles("the counterparty LEI must be a valid twenty character identifier issued by a LOU " * 3)
    assert abs(minhash_similarity(minhash_signature(a), minhash_signature(b)) - jaccard(a, b)) < 0.25
