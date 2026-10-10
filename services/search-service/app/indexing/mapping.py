"""Elasticsearch index settings and mappings for regulatory paragraphs.

Analyzers
---------
``reg_text``     char filter ``_`` -> space (so ``Counterparty_LEI`` is found by
                 "counterparty lei"), standard tokenizer, lowercase, ASCII folding,
                 possessive removal, light English stemming (KStem).
``reg_exact``    same as reg_text but without stemming; used for exact phrases.
``reg_text_syn`` search-time only: reg_text plus the synonym graph from
                 config/synonyms.txt.

Fields
------
content / heading            BM25 text (reg_text)
  .exact                     unstemmed, for "quoted phrases" and phrase boosts
  .syn                       synonym-expanded at query time
heading_suggest              search_as_you_type copy of the heading, for suggestions
document_name, regulator ... keyword (+ text where useful) for filters/facets
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

INDEX_VERSION = 1


def load_synonyms(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append(line)
    return rules


def index_body(synonyms: list[str]) -> dict[str, Any]:
    text_with_subfields = {
        "type": "text",
        "analyzer": "reg_text",
        "fields": {
            "exact": {"type": "text", "analyzer": "reg_exact"},
            "syn": {"type": "text", "analyzer": "reg_text", "search_analyzer": "reg_text_syn"},
        },
    }
    return {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": 0, "max_result_window": 10000},
            "analysis": {
                "char_filter": {"underscore_to_space": {"type": "pattern_replace", "pattern": "_", "replacement": " "}},
                "filter": {
                    "reg_possessive": {"type": "stemmer", "language": "possessive_english"},
                    "reg_light_stem": {"type": "stemmer", "language": "light_english"},
                    "reg_synonyms": {"type": "synonym_graph", "synonyms": synonyms, "lenient": True},
                },
                "analyzer": {
                    "reg_text": {
                        "type": "custom",
                        "char_filter": ["underscore_to_space"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "reg_possessive", "reg_light_stem"],
                    },
                    "reg_exact": {
                        "type": "custom",
                        "char_filter": ["underscore_to_space"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    },
                    "reg_text_syn": {
                        "type": "custom",
                        "char_filter": ["underscore_to_space"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "reg_synonyms", "reg_possessive", "reg_light_stem"],
                    },
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "paragraph_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "document_version_id": {"type": "keyword"},
                "document_name": {
                    "type": "text",
                    "analyzer": "reg_text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "document_title": {"type": "text", "analyzer": "reg_text"},
                "regulator": {
                    "type": "keyword",
                    "fields": {"text": {"type": "text", "analyzer": "reg_text"}},
                },
                "jurisdiction": {"type": "keyword"},
                "category": {"type": "keyword"},
                "version": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "effective_date": {"type": "date", "format": "strict_date"},
                "uploaded_at": {"type": "date"},
                "is_latest": {"type": "boolean"},
                "ordinal": {"type": "integer"},
                "page_start": {"type": "integer"},
                "page_end": {"type": "integer"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
                "anchor": {"type": "keyword", "index": False},
                "section_heading": {
                    **text_with_subfields,
                    "fields": {
                        **text_with_subfields["fields"],
                        "keyword": {"type": "keyword", "ignore_above": 512},
                    },
                },
                "heading_suggest": {"type": "search_as_you_type", "analyzer": "reg_exact"},
                "content": text_with_subfields,
                "content_hash": {"type": "keyword"},
                "char_count": {"type": "integer"},
                "indexed_at": {"type": "date"},
            },
        },
    }
