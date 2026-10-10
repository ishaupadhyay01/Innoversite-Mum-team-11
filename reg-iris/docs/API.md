# REST API specification (v1)

* Base URL (through the gateway): `http://localhost:8080`. All public routes are under `/api/v1/…`.
* Interactive Swagger UI per service: **ingestion** `:8001/docs`, **search** `:8002/docs`, **rules** `:8003/docs`.
  Raw specs via the gateway: `/openapi/ingestion.json`, `/openapi/search.json`, `/openapi/rules.json`.
* Auth: if `API_TOKEN` is set, send `Authorization: Bearer <token>` (health routes are always open).
* Correlation: send/receive `X-Request-ID`.
* Uploads are `multipart/form-data` with the file in field `file`.

## Conventions

**Pagination** — `?page=1&size=25` (max 500) → `{"items": [...], "total": 123, "page": 1, "size": 25, "pages": 5}`.
**List filters** — repeat the key: `?regulator=EMIR&regulator=FCA`.
**Errors** — every non-2xx response:

```json
{"error": {"code": "DUPLICATE_DOCUMENT",
           "message": "An identical file has already been uploaded",
           "details": {"document_id": "…", "version_id": "…", "version_label": "v1.0"},
           "request_id": "3f2c…"}}
```

| HTTP | Typical `code` |
|---|---|
| 401 | `UNAUTHORIZED` |
| 404 | `NOT_FOUND` |
| 409 | `DUPLICATE_DOCUMENT`, `VERSION_NOT_READY`, `DATASET_INVALID` |
| 413 | `PAYLOAD_TOO_LARGE` |
| 422 | `REQUEST_VALIDATION_FAILED`, `UNSUPPORTED_FILE`, `EMPTY_FILE`, `INVALID_RULE_FILE`, `NO_RULES`, `NO_PREVIOUS_VERSION` |
| 501 | `SEMANTIC_DISABLED` |
| 502 | `UPSTREAM_ERROR` |

### Definition-of-Done endpoint map
| Brief asks for | Endpoint |
|---|---|
| search | `GET /api/v1/search` |
| gap-analysis | `GET /api/v1/runs/{id}/results?status=FAIL` (+ `/stats`) |
| impact-matrix | `GET /api/v1/runs/{id}/results`, `/matrix`, `/export.csv` |
| checklist | `GET /api/v1/rule-sets/{id}` (rules with clause links) and `POST /api/v1/evaluate` |
| alerts | `GET /api/v1/alerts`, `GET /api/v1/whats-new` |

---

## Module 1 — Ingestion & Versioning (`ingestion-service`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/documents/match-suggestions` | Pre-upload check: exact duplicate + similar existing documents. Form: `file`, `regulator?`, `title?` |
| `POST` | `/api/v1/documents` | Upload a **new** document → `202` (document + version 1). Form: `file`, `regulator`*, `title`, `jurisdiction`, `category`, `effective_date` (YYYY-MM-DD), `version_label`, `activate` (default true) |
| `POST` | `/api/v1/documents/{document_id}/versions` | Upload an **updated** version → `202`. Form: `file`, `version_label`, `effective_date`, `activate` |
| `GET` | `/api/v1/documents` | List; filters `q`, `regulator`, `jurisdiction`, `category`, `has_active`; paginated |
| `GET` | `/api/v1/documents/stats` | Dashboard counters |
| `GET` | `/api/v1/documents/{document_id}` | Document + full version history |
| `PATCH` | `/api/v1/documents/{document_id}` | Edit metadata |
| `GET` | `/api/v1/documents/{document_id}/versions` | Version history, newest first |
| `GET` | `/api/v1/versions/{version_id}` | Version (poll `processing_status` after upload) |
| `GET` | `/api/v1/versions/{version_id}/clauses` | Parsed clauses with page spans / anchors |
| `GET` | `/api/v1/versions/{version_id}/pages/{n}` | Page text |
| `GET` | `/api/v1/versions/{version_id}/file` | Original file inline — append `#page=N` (PDF) or `#anchor` (HTML) |
| `POST` | `/api/v1/versions/{version_id}/activate` | Make ACTIVE (previous ACTIVE → INACTIVE). Also used for rollback |
| `POST` | `/api/v1/versions/{version_id}/deactivate` | Make INACTIVE |
| `GET` | `/api/v1/versions/{version_id}/diff?against=&include_unchanged=` | Clause diff vs another version of the same document (default: previous) |
| `GET` | `/api/v1/versions/{version_id}/audit` | Audit trail |
| `GET` | `/api/v1/whats-new?regulator=` | What's New cards, newest first; paginated |
| `GET` | `/api/v1/whats-new/{card_id}` | One card |
| `GET` | `/api/v1/alerts?unread_only=` | Alert feed |
| `POST` | `/api/v1/alerts/{alert_id}/read`, `/api/v1/alerts/read-all` | Mark read |
| `GET` | `/internal/v1/versions/{version_id}/index-payload` | **Internal** — metadata + clauses for search-service |

Example — match suggestions (values illustrative)
```http
POST /api/v1/documents/match-suggestions   (file=EMIR_2021_v2.pdf, regulator=EMIR)
```
```json
{"sha256": "9b1…", "recommendation": "NEW_VERSION", "exact_duplicate": null,
 "candidates": [{"document_id": "…", "title": "EMIR — Trade reporting", "regulator": "EMIR",
                 "active_version_label": "v1.0", "score": 0.74,
                 "reasons": ["62% content overlap with v1.0", "similar file name", "same regulator (EMIR)"]}]}
```

Example — What's New card
```json
{"card_type": "NEW_VERSION", "regulator": "MiFID II", "title": "MiFID II — Trade reporting",
 "effective_date": "2023-07-01",
 "headline": "v1.0 → v2.0: Added Paragraph 7 (New Clause – Execution Venue Disclosure (v2.0)).",
 "summary": {"ADDED": 1, "REMOVED": 0, "MODIFIED": 0, "UNCHANGED": 6},
 "highlights": [{"clause_ref": "Paragraph 7", "change": "ADDED", "page": 2, "excerpt": "Effective 1 July 2023, …"}]}
```

---

## Module 2 — Search & Comparison (`search-service`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/search` | `q`*, `mode=keyword\|semantic`, `regulator[]`, `jurisdiction[]`, `category[]`, `status=ACTIVE\|INACTIVE\|ALL` (default ACTIVE), `effective_from`, `effective_to`, `document_id`, `page`, `size` (≤100) |
| `GET` | `/api/v1/search/facets` | Values + counts for regulator / jurisdiction / category / status |
| `GET` | `/api/v1/search/index-status` | Which versions are indexed (keyword / semantic) |
| `POST` | `/api/v1/search/reindex/{version_id}` | Synchronous re-index (recovery) |
| `POST` | `/api/v1/compare` | `{left_version_id, right_version_id, include_unchanged}` — any two versions, same or different regulation |
| `GET` | `/api/v1/compare/{comparison_id}` | Saved comparison |

Example — search hit
```json
{"clause_id": "…", "score": 7.91, "status": "ACTIVE", "effective_date": "2023-07-01",
 "text": "The Counterparty_LEI must be a valid 20-character alphanumeric identifier …",
 "highlights": ["The <mark>Counterparty_LEI</mark> must be a valid 20-character …"],
 "citation": {"document_title": "MiFID II — Trade reporting", "file_name": "MiFID_II_2023_v2.pdf",
              "regulator": "MiFID II", "version_label": "v2.0", "clause_ref": "Paragraph 3",
              "clause_title": "Counterparty LEI Requirement", "page": 1, "anchor": null,
              "file_url": "/api/v1/versions/<version_id>/file#page=1",
              "label": "MiFID_II_2023_v2.pdf (v2.0), Paragraph 3, p.1"}}
```
Highlights are HTML-escaped except for `<mark>` tags.

---

## Module 3 — Rules & Impact Analysis (`rules-engine-service`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/rule-sets/validate` | Dry-run validation + lint of a rules JSON |
| `POST` | `/api/v1/rule-sets` | Upload rules JSON → new ACTIVE rule set for its regulator (`201`; identical re-upload returns `already_uploaded: true`). Form: `file`, `source_document_id?` |
| `GET` | `/api/v1/rule-sets?status=ACTIVE\|INACTIVE\|ALL&regulator=` | List |
| `GET` | `/api/v1/rule-sets/{rule_set_id}` | Rule set with rules, lint, clause links |
| `POST` | `/api/v1/rule-sets/{rule_set_id}/link-clauses` | Re-run auto-linking to clauses (`202`) |
| `GET` | `/api/v1/rules/{rule_id}` | One rule |
| `PUT` | `/api/v1/rules/{rule_id}/clause-link` | Confirm/override the source clause (`{clause_ref, document_id, version_id, page, citation_label, file_url}`) |
| `POST` | `/api/v1/datasets` | Upload trade CSV → validation report (`201`, idempotent) |
| `GET` | `/api/v1/datasets`, `/api/v1/datasets/{id}` | List / get |
| `GET` | `/api/v1/schemas/trade-reporting` | Reporting schema in use |
| `POST` | `/api/v1/runs` | `{dataset_id, rule_set_ids?: [], document_version_id?}` → `202` QUEUED (empty `rule_set_ids` = all ACTIVE) |
| `GET` | `/api/v1/runs`, `/api/v1/runs/{id}` | Status & progress (`chunks_done/chunks_total`) |
| `GET` | `/api/v1/runs/{id}/stats` | Totals, pass rate, by rule / regulator / asset class |
| `GET` | `/api/v1/runs/{id}/results` | Flat matrix. Filters: `status[]`, `rule_code[]`, `regulator[]`, `severity[]`, `asset_class[]`, `trade_id`, `q` (explanation text); `sort=row_number\|trade_id\|rule_code\|status\|severity\|regulator`, `desc`; paginated |
| `GET` | `/api/v1/runs/{id}/matrix?only_failing=` | Pivot: trades × rules (`cells: {"MIFID-2": "FAIL", …}`); paginated by trade |
| `GET` | `/api/v1/runs/{id}/export.csv` | Streaming CSV (same filters as `/results`) |
| `POST` | `/api/v1/evaluate` | `{trade: {...}, rule_set_ids?: []}` → synchronous outcomes for one trade |

Rules file format (backward compatible with the sample files; optional fields in *italics*)
```json
{"regulator": "MiFID II", "jurisdiction": "EU",
 "rules": [{"id": "MIFID-2", "description": "Price must be non-negative.",
            "logic": {">=": [{"var": "Price"}, 0]},
            "impact": "Field Price cannot be negative.",
            "severity": "HIGH",
            "applies_when": {"in": [{"var": "Asset_Class"}, ["Equity", "Bond"]]},
            "source": {"clause_ref": "Paragraph 6"}}]}
```
Operators: all standard JSONLogic + `regex` (field name or expression, pattern), `toNumber` (ISO dates → YYYYMMDD),
`isDate`, `dateDiffDays`, `length`, `lower`, `upper`, `isValidLEI` (ISO 17442 checksum), `isValidISIN` (ISO 6166).

Example — result row
```json
{"trade_id": "T000004", "row_number": 4, "asset_class": "Bond", "rule_code": "MIFID-2", "regulator": "MiFID II",
 "severity": "HIGH", "status": "FAIL",
 "explanation": "Price (-99.9) must be ≥ 0 — required by MiFID II rule MIFID-2 (MiFID_II_2023_v2.pdf (v2.0), Paragraph 5, p.1 — suggested source, unconfirmed). Field Price cannot be negative.",
 "field_values": {"Price": -99.9}, "clause_ref": "Paragraph 5",
 "citation_label": "MiFID_II_2023_v2.pdf (v2.0), Paragraph 5, p.1 — suggested source, unconfirmed"}
```

Result statuses: `PASS`, `FAIL`, `NOT_APPLICABLE` (out of the rule's scope: `applies_when` false or a top-level
`if` that resolves to literal `true`), `ERROR` (rule could not be evaluated).
