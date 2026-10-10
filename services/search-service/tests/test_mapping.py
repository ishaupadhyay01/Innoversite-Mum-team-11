"""Index mapping and analyzers."""

from __future__ import annotations

from app.indexing.mapping import index_body, load_synonyms

from .conftest import CONFIG


def test_synonyms_loaded_from_config() -> None:
    syn = load_synonyms(CONFIG / "synonyms.txt")
    assert "lei, legal entity identifier" in syn
    assert all(not s.startswith("#") for s in syn)


def test_mapping_defines_bm25_fields_filters_and_strict_schema() -> None:
    body = index_body(["lei, legal entity identifier"])
    analysis = body["settings"]["analysis"]
    assert analysis["char_filter"]["underscore_to_space"]["pattern"] == "_"
    assert "reg_synonyms" in analysis["analyzer"]["reg_text_syn"]["filter"]
    assert "reg_light_stem" not in analysis["analyzer"]["reg_exact"]["filter"]
    props = body["mappings"]["properties"]
    assert body["mappings"]["dynamic"] == "strict"
    assert props["content"]["fields"]["syn"]["search_analyzer"] == "reg_text_syn"
    assert props["content"]["fields"]["syn"]["analyzer"] == "reg_text"  # synonyms only at query time
    for keyword in ("regulator", "jurisdiction", "category", "version", "source_type", "document_version_id"):
        assert props[keyword]["type"] == "keyword"
    assert props["effective_date"]["type"] == "date"
    assert props["page_start"]["type"] == "integer"
    assert props["heading_suggest"]["type"] == "search_as_you_type"
