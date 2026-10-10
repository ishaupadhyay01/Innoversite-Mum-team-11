# Data model

Database-per-service on one PostgreSQL 16 instance (separate instances in production). No foreign keys cross
service boundaries — cross-service references (e.g. `validation_runs.document_version_id`) are plain UUIDs resolved
over REST. Every schema change is an Alembic migration in the owning service (`services/<svc>/migrations`).

Conventions: UUID primary keys (except append-only high-volume tables → `BIGINT` identity), `timestamptz` everywhere,
JSONB for flexible payloads, status columns as `VARCHAR` + `CHECK` constraint (cheaper to evolve than PG enums).

## 1. `iris_ingestion` (ingestion-service)

```mermaid
erDiagram
  documents ||--o{ document_versions : "has versions"
  documents |o--o| document_versions : "active_version_id"
  document_versions ||--o{ document_pages : contains
  document_versions ||--o{ clauses : "split into"
  document_versions |o--o{ document_versions : "parent_version_id"
  documents ||--o{ version_diffs : ""
  document_versions ||--o{ version_diffs : "from / to"
  documents ||--o{ whats_new_cards : ""
  version_diffs |o--o{ whats_new_cards : ""
  whats_new_cards ||--o{ alerts : ""

  documents {
    uuid id PK
    varchar document_key UK "slug"
    varchar title
    varchar regulator
    varchar regulator_canonical "e.g. DODD-FRANK"
    varchar jurisdiction
    varchar category
    uuid active_version_id FK
    timestamptz created_at
    timestamptz updated_at
  }
  document_versions {
    uuid id PK
    uuid document_id FK
    uuid parent_version_id FK
    int version_number "unique per document"
    varchar version_label "v1.0"
    varchar status "ACTIVE | INACTIVE"
    varchar processing_status "UPLOADED | PROCESSING | READY | FAILED"
    bool activate_on_ready
    varchar original_filename
    varchar storage_key "sha[:2]/sha.ext"
    varchar mime_type
    bigint file_size
    varchar sha256 UK "exact-duplicate detection"
    date effective_date
    int page_count
    int clause_count
    jsonb fingerprint "MinHash(64)"
    jsonb quality_warnings
    text error_message
    timestamptz uploaded_at
    timestamptz processed_at
    timestamptz activated_at
  }
  document_pages {
    bigint id PK
    uuid version_id FK
    int page_number
    text text
  }
  clauses {
    uuid id PK
    uuid version_id FK
    int ordinal
    varchar clause_ref "Paragraph 3 / Section 2 / Q5"
    varchar title
    text text
    int page_start
    int page_end
    varchar anchor "HTML id"
    varchar text_hash
  }
  version_diffs {
    uuid id PK
    uuid document_id FK
    uuid from_version_id FK
    uuid to_version_id FK
    jsonb summary
    jsonb changes
  }
  whats_new_cards {
    uuid id PK
    varchar card_type "NEW_DOCUMENT | NEW_VERSION"
    uuid document_id FK
    uuid version_id FK
    uuid diff_id FK
    varchar regulator
    varchar title
    date effective_date
    text headline
    jsonb summary
    jsonb highlights
  }
  alerts {
    uuid id PK
    uuid card_id FK
    varchar level
    text message
    timestamptz read_at
  }
  audit_log {
    bigint id PK
    varchar entity_type
    varchar entity_id
    varchar action
    varchar actor
    jsonb payload
    varchar request_id
  }
```

Key constraints
* `uq_document_versions_one_active` — **partial unique index** `(document_id) WHERE status = 'ACTIVE'`: at most one
  ACTIVE version per document, guaranteed by the database even under concurrent activations.
* `document_versions.sha256` unique — exact duplicates are rejected atomically.
* `uq_document_versions_number (document_id, version_number)`, `uq_clauses_ref (version_id, clause_ref)`,
  `uq_version_diffs_pair (from_version_id, to_version_id)`.
* `documents.active_version_id ↔ document_versions.id` is circular; the FK is added after both tables exist
  (`use_alter`) and is `ON DELETE SET NULL`.

## 2. `iris_search` (search-service)

| Table | Purpose |
|---|---|
| `indexed_versions` (`version_id` PK, `document_id`, `status`, `clause_count`, `keyword_indexed`, `semantic_indexed`, `last_error`, `indexed_at`) | Index bookkeeping — which versions are in ES/Chroma, for re-index and health |
| `search_query_log` (`id` bigint, `query`, `mode`, `filters` jsonb, `result_count`, `took_ms`, `created_at`) | Search analytics, zero-result queries |
| `comparisons` (`id`, `left_version_id`, `right_version_id`, labels, `summary`, `changes` jsonb) | Saved comparisons (shareable by id) |

### Elasticsearch index `iris-clauses` (alias → `iris-clauses-v1`)
One document per clause; `_id` = clause id. Mapping: `services/search-service/app/backends/es_mapping.json`
(`dynamic: strict`).

| Field | Type | Use |
|---|---|---|
| `text`, `clause_title`, `document_title` | `text` (custom `reg_text` analyzer: lowercase, ascii-folding, English stop + stemmer) | full-text match + highlight |
| `clause_ref` | `keyword` + `.text` | exact and fuzzy clause lookup ("Paragraph 3") |
| `regulator`, `regulator_canonical`, `jurisdiction`, `category`, `status`, `version_label`, `file_name`, `mime_type` | `keyword` | filters & facets |
| `effective_date` | `date` | range filter |
| `document_id`, `version_id`, `clause_id` | `keyword` | joins back to ingestion, status flips |
| `page_start`, `page_end`, `ordinal`, `anchor` | numeric / non-indexed keyword | citations |

### ChromaDB collection `iris-clauses` (optional)
id = clause id, embedding = MiniLM(`title. text`), metadata = the same filter fields as ES (cosine space).

## 3. `iris_rules` (rules-engine-service)

```mermaid
erDiagram
  rule_sets ||--o{ rules : contains
  rules ||--o| rule_clause_links : "traced to"
  trade_datasets ||--o{ validation_runs : "analysed by"
  validation_runs ||--o{ validation_results : produces

  rule_sets {
    uuid id PK
    varchar name
    varchar regulator
    varchar regulator_canonical
    varchar jurisdiction
    int version_number "unique per regulator"
    varchar status "ACTIVE | INACTIVE"
    varchar source_filename
    varchar sha256 UK
    jsonb raw "uploaded file"
    jsonb lint
    int rule_count
    uuid source_document_id "ingestion doc (by ref)"
  }
  rules {
    uuid id PK
    uuid rule_set_id FK
    int ordinal
    varchar code "MIFID-1 (unique per set)"
    text description
    jsonb logic "JSONLogic"
    jsonb applies_when
    text impact
    varchar severity
    jsonb fields
    bool enabled
    varchar declared_clause_ref
  }
  rule_clause_links {
    uuid id PK
    uuid rule_id FK "unique"
    uuid document_id
    uuid version_id
    uuid clause_id
    varchar clause_ref
    int page
    varchar citation_label
    varchar file_url
    text excerpt
    varchar method "MANUAL | AUTO_SEARCH"
    float score
    bool confirmed
  }
  trade_datasets {
    uuid id PK
    varchar filename
    varchar storage_key
    varchar sha256 UK
    bigint file_size
    int row_count
    varchar status "VALID | VALID_WITH_WARNINGS | INVALID"
    jsonb validation "report"
  }
  validation_runs {
    uuid id PK
    uuid dataset_id FK
    jsonb rule_set_ids
    uuid document_version_id "ingestion version (by ref)"
    varchar status "QUEUED | RUNNING | COMPLETED | FAILED"
    jsonb rule_snapshot "rules as evaluated"
    int total_trades
    int total_rules
    int chunks_total
    int chunks_done
    jsonb summary
    text error_message
  }
  validation_results {
    bigint id PK
    uuid run_id FK
    int row_number
    varchar trade_id
    varchar asset_class
    uuid rule_id
    varchar rule_code
    varchar regulator
    varchar severity
    varchar status "PASS | FAIL | NOT_APPLICABLE | ERROR"
    text explanation
    jsonb field_values
    varchar clause_ref
    varchar citation_label
    uuid source_version_id
  }
```

Key constraints & indexes
* `uq_rule_sets_one_active` — partial unique `(regulator_canonical) WHERE status='ACTIVE'`.
* `validation_results`: `ix_results_run_status`, `ix_results_run_trade`, `ix_results_run_rule` serve the matrix
  filters, pivot and export; `CHECK status IN (…)`.
* Lineage chain for any FAIL: `validation_results → rule_code / rule_id → rule_clause_links (clause, page, version)`
  plus `validation_runs.rule_snapshot` (exact logic used) and `document_version_id`.

## 4. File storage
| Volume | Owner | Layout |
|---|---|---|
| `regulations` → `/data/regulations` | ingestion | content-addressed `ab/abcdef….pdf` |
| `rulesdata` → `/data/rules-engine` | rules | content-addressed `ab/abcdef….csv` |

`FileStorage` is a protocol — swap `LocalFileStorage` for S3/MinIO without touching business code.
