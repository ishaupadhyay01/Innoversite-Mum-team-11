# Reg IRIS — API reference

Base URL: `http://localhost:8000` (gateway; the UI reaches the same paths at `http://localhost:3000/api/...`).
Interactive documentation: **`/api/docs`** (Swagger UI, all services merged) and `/api/openapi.json`.

Conventions

- JSON in and out, except uploads (multipart) and exports (CSV).
- Errors: `{"error": {"code": "document_not_found", "message": "...", "details": null, "request_id": "a1b2..."}}` with a matching HTTP status (400, 401, 404, 409, 413, 422, 500, 503).
- Validation errors: status 422, `code: "validation_error"`, `details` lists `{loc, msg, type}`.
- Every response carries `x-request-id` and `x-response-time-ms`.
- If the gateway runs with `API_TOKEN`, these require `Authorization: Bearer <token>`: `POST /api/documents/upload`, `POST /api/imports/run`, `POST /api/rules/reload`, `POST /api/impact-matrix`, `PATCH /api/alerts/{id}/read`, `POST /api/alerts/read-all`.

Example values below for the rules engine come from the supplied dataset; search scores and ids are illustrative.

## Endpoint map

| Method | Path | Service | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | gateway | Liveness |
| GET | `/api/system/status` | gateway | Health of services, Elasticsearch, PostgreSQL, rules, import |
| GET | `/api/dashboard/stats` | gateway | Aggregated dashboard figures |
| POST | `/api/documents/upload` | ingestion | Upload PDF/HTML/TXT (async job) |
| GET | `/api/documents/uploads`, `/api/documents/uploads/{job_id}` | ingestion | Upload job status |
| GET | `/api/documents` | ingestion | Document families (filters, pagination) |
| GET | `/api/documents/stats` | ingestion | Repository counts |
| GET | `/api/documents/match` | ingestion | Suggest a family for a file name |
| GET | `/api/documents/{id}` | ingestion | Family with all versions |
| GET | `/api/documents/{id}/versions` | ingestion | Version history |
| GET | `/api/documents/{id}/source` | ingestion | Original file (`?version_id=`, `?download=true`) |
| GET | `/api/documents/versions/{version_id}` | ingestion | Version detail with extracted clauses |
| GET | `/api/documents/compare` | ingestion | Clause-level diff of two versions |
| GET | `/api/alerts` | ingestion | Alerts (filters, unread count) |
| GET | `/api/alerts/unread-count` | ingestion | Counter for polling |
| GET | `/api/alerts/{id}` | ingestion | Alert detail |
| PATCH | `/api/alerts/{id}/read` | ingestion | Mark read / unread |
| POST | `/api/alerts/read-all` | ingestion | Mark all read |
| GET | `/api/imports/latest` · POST `/api/imports/run` | ingestion | Dataset import status / re-run |
| GET | `/api/audit` | ingestion | Audit trail (all services) |
| POST | `/api/search` | search | BM25 keyword search |
| GET | `/api/search/suggestions` | search | Search-as-you-type |
| GET | `/api/search/filters` | search | Filter values from the index |
| GET | `/api/search/paragraphs/{paragraph_id}` | search | Exact paragraph with context |
| GET | `/api/search/versions/{version_id}/paragraphs` | search | All indexed paragraphs of a version |
| GET | `/api/search/analytics` | search | Query history and response times |
| GET | `/api/rules` | rules | Rule sets, rules, schema, overlay |
| GET | `/api/rules/operators` | rules | Supported operators |
| GET | `/api/rules/{rule_id}` | rules | Rule detail + related text |
| POST | `/api/rules/validate` | rules | Validate a rule-set document (not saved) |
| POST | `/api/rules/reload` | rules | Reload rule files from disk |
| POST | `/api/impact-matrix` | rules | Run an impact analysis |
| GET | `/api/impact-matrix`, `/api/impact-matrix/latest` | rules | Runs |
| GET | `/api/impact-matrix/{analysis_id}` | rules | Matrix rows (filter / sort / page) |
| GET | `/api/impact-matrix/{analysis_id}/results/{result_id}` | rules | One row with trade, rule, related text |
| GET | `/api/impact-matrix/{analysis_id}/export` | rules | CSV export (same filters) |
| GET | `/api/impact-matrix/{analysis_id}/export/summary` | rules | Summary CSV |
| GET | `/api/impact-matrix/{analysis_id}/trades` | rules | One verdict per trade: selected rules combined with AND |
| GET | `/api/impact-matrix/{analysis_id}/export/trades` | rules | Per-trade AND verdicts as CSV |
| POST | `/api/gap-analysis` | rules | Gap analysis |
| GET | `/api/checklist` | rules | Compliance checklist |
| GET | `/api/trades/datasets`, `/api/trades`, `/api/trades/{trade_id}` | rules | Trade data |
| POST | `/api/trades/query` | rules | Structured answer to a supported trade question |

## Search

`POST /api/search`

```json
{
  "query": "Counterparty LEI",
  "filters": {"regulators": ["MiFID II"], "jurisdictions": [], "categories": [], "source_types": [],
              "versions": [], "effective_from": null, "effective_to": null},
  "scope": "latest",
  "version_id": null,
  "sort": "relevance",
  "match_mode": "smart",
  "page": 1,
  "page_size": 10
}
```

- `query`: keywords; `"double quotes"` for exact phrases; `-word` to exclude. Empty query + filters = browse.
- `scope`: `latest` (default), `all` (includes superseded versions), `version` (requires `version_id`).
- `sort`: `relevance` | `newest` | `effective_date` | `document_name`.
- `match_mode`: `smart` (all terms up to three, then 75 %), `all`, `any`.

Response (abbreviated):

```json
{
  "query": "Counterparty LEI",
  "interpreted": {"terms": ["Counterparty", "LEI"], "phrases": [], "excluded": [], "match_mode": "smart"},
  "total": 3, "took_ms": 21.4, "es_took_ms": 6,
  "page": 1, "page_size": 10, "total_pages": 1,
  "scope": "latest", "sort": "relevance", "relaxed": false,
  "results": [{
    "paragraph_id": "v2-p0003",
    "score": 6.91,
    "regulator": "MiFID II",
    "is_latest": true,
    "heading": "Paragraph 3. Counterparty LEI Requirement",
    "heading_segments": [{"text": "Paragraph 3. ", "highlight": false}, {"text": "Counterparty", "highlight": true},
                         {"text": " ", "highlight": false}, {"text": "LEI", "highlight": true},
                         {"text": " Requirement", "highlight": false}],
    "text_segments": [{"text": "The ", "highlight": false}, {"text": "Counterparty", "highlight": true}, "…"],
    "citation": {
      "regulator": "MiFID II", "document_name": "MiFID_II_2023_v2.pdf", "version": "v2.0",
      "source_type": "pdf", "page_start": 1, "page_end": 1, "location_label": "Page 1",
      "section_heading": "Paragraph 3. Counterparty LEI Requirement",
      "source_url": "/api/documents/1/source?version_id=2#page=1",
      "viewer_url": "/viewer/2?paragraph=v2-p0003"
    },
    "identical_text_in": [{"paragraph_id": "v1-p0003", "document_name": "MiFID_II_2023_v1.pdf", "version": "v1.0", "location_label": "Page 1"}]
  }],
  "facets": {"regulator": [{"value": "MiFID II", "count": 3}, {"value": "SEC", "count": 2}]},
  "did_you_mean": null,
  "notices": []
}
```

HTML citations have `page_start: null` and `location_label: "Section #p3"`; TXT citations use `line_start`/`line_end` (`"Lines 9–10"`).

`GET /api/search/suggestions?q=coun` → `[{"text": "Paragraph 3. Counterparty LEI Requirement", "type": "heading", "detail": "MiFID_II_2023_v2.pdf"}, {"text": "counterparty lei", "type": "history", "detail": "recent search"}]`

## Documents and versions

Upload a new document:

```bash
curl -F file=@guidance.pdf -F regulator=ESMA -F jurisdiction=EU -F category="Trade reporting" \
     -F effective_date=2025-01-01 localhost:8000/api/documents/upload
```

Upload a new version of document 1:

```bash
curl -F file=@demo/MiFID_II_2023_v3_DEMO.txt -F document_id=1 -F version_label=v3.0 localhost:8000/api/documents/upload
```

```json
{"job_id": "8d0c…", "status": "queued", "status_url": "/api/documents/uploads/8d0c…"}
```

`GET /api/documents/uploads/8d0c…` → `{"status": "indexed", "detail": "Indexed 9 clause(s)", "document_id": 1, "version_id": 11, …}` (or `"failed"` with the reason, e.g. `"Extraction failed: No extractable text found in PDF …"`).

Rejections are immediate: `400 unsupported_type`, `400 invalid_content` (e.g. a `.pdf` without a PDF header), `413 file_too_large`, `409 duplicate_version` / `duplicate_document` (identical bytes already stored), `409 version_label_exists`, `422 regulator_required`.

`GET /api/documents/compare?base_version_id=1&target_version_id=2`

```json
{
  "same_document": true,
  "stats": {"unchanged": 6, "added": 1, "removed": 0, "modified": 0, "old_clauses": 6, "new_clauses": 7},
  "summary": "1 clause added: “Paragraph 7. New Clause – Execution Venue Disclosure (v2.0)” (p. 2). 6 unchanged.",
  "change_types": ["Added Clause"],
  "rows": [{"change": "added", "old": null, "new": {"ordinal": 7, "heading": "Paragraph 7. …", "page_start": 2, "location": "p. 2", "…": "…"}, "similarity": null, "inline": null}],
  "method": "difflib.SequenceMatcher over clauses; …"
}
```

## Alerts

`GET /api/alerts?unread_only=true&q=MiFID&change_type=Added%20Clause&page=1&page_size=20`

```json
{
  "items": [{
    "id": 11, "change_type": "New Version", "change_types": ["New Version", "Added Clause", "Modified Clause"],
    "title": "MiFID II: MiFID_II_2023_v3_DEMO.txt (v2.0 → v3.0)", "regulator": "MiFID II",
    "previous_version_label": "v2.0", "new_version_label": "v3.0", "effective_date": "2023-07-01",
    "summary": "2 clauses added: …. 1 clause modified: “Paragraph 5. Timing of Reporting” (lines 16–17). 6 unchanged.",
    "source": "upload", "is_read": false, "event_time": "2026-10-10T09:12:03Z"
  }],
  "total": 1, "unread": 1, "page": 1, "page_size": 20
}
```

`PATCH /api/alerts/11/read` with `{"is_read": true}` → the updated alert.

## Rules and impact analysis

`POST /api/impact-matrix`

```json
{"dataset": "sample_trades.csv", "regulators": [], "rule_ids": [], "run_async": false, "include_related_text": true}
```

→ `201`

```json
{
  "id": "f3a1…", "status": "completed", "dataset": "sample_trades.csv", "duration_ms": 412.0,
  "summary": {
    "total_trades": 200, "total_rules": 8, "total_evaluations": 1600,
    "status_counts": {"PASS": 1021, "FAIL": 209, "NOT_APPLICABLE": 370, "ERROR": 0},
    "unique_impacted_trades": 156, "fully_compliant_trades": 44, "trade_compliance_rate": 0.22,
    "by_regulator": [{"regulator": "EMIR", "pass": 222, "fail": 13, "not_applicable": 165, "error": 0, "impacted_trades": 12}, "…"],
    "by_rule": [{"rule_id": "MIFID-2", "fail": 8, "…": "…"}, "…"],
    "by_category": [{"category": "missing_value", "label": "Missing required values", "count": 164}, "…"]
  }
}
```

The summary also contains `combined`: the selected rules combined with **AND** per trade.

```json
"combined": {
  "logic": "AND", "rule_ids": ["EMIR-1", "EMIR-2", "FCA-1", "FCA-2", "MIFID-1", "MIFID-2", "MIFID-3", "MIFID-4"],
  "expression": "EMIR-1 AND EMIR-2 AND FCA-1 AND FCA-2 AND MIFID-1 AND MIFID-2 AND MIFID-3 AND MIFID-4",
  "trades": 200, "status_counts": {"PASS": 44, "FAIL": 156, "NOT_APPLICABLE": 0, "ERROR": 0},
  "compliant_trades": 44, "non_compliant_trades": 156, "undetermined_trades": 0, "compliance_rate": 0.22
}
```

`GET /api/impact-matrix/{id}/trades?overall=FAIL&trade_id=T0000&asset_class=Bond&failed_rule=MIFID-2&page=1&page_size=25` returns one verdict per trade (`overall`: `FAIL` if any selected rule fails, else `ERROR` if any could not be evaluated, else `PASS`, or `NOT_APPLICABLE` when no selected rule applies):

```json
{
  "combined": {"expression": "EMIR-1 AND … AND MIFID-4", "compliant_trades": 44, "…": "…"},
  "items": [{
    "trade_id": "T000004", "asset_class": "Bond", "overall": "FAIL", "compliant": false, "rules_evaluated": 8,
    "failed_rule_ids": ["FCA-2", "MIFID-2"], "error_rule_ids": [], "passed_rule_ids": ["…"], "not_applicable_rule_ids": ["…"],
    "failures": [{"rule_id": "MIFID-2", "regulator": "MiFID II", "status": "FAIL", "affected_fields": ["Price"], "explanation": "Price is -99.9, which fails Price >= 0. …"}, "…"],
    "reason": "Fails 2 of 8 selected rule(s): FCA-2, MIFID-2."
  }],
  "total": 156, "page": 1, "page_size": 25, "total_pages": 7
}
```

`GET /api/impact-matrix/{id}/export/trades` (same filters) downloads these verdicts as CSV; the summary CSV gains a "Trades (rules combined with AND)" row.

With `"run_async": true` the response is `202 {"id": "…", "status": "queued", "status_url": "/api/impact-matrix/…"}`.

`GET /api/impact-matrix/{id}?status=FAIL&regulator=MiFID%20II&trade_id=T00000&sort_by=trade_id&sort_dir=asc&page=1&page_size=25`

```json
{
  "items": [{
    "id": 25, "trade_id": "T000004", "asset_class": "Bond", "regulator": "MiFID II", "rule_id": "MIFID-2",
    "rule_description": "Price must be non‑negative.", "status": "FAIL",
    "affected_fields": ["Price"], "actual_values": {"Price": -99.9},
    "expected_condition": "Price >= 0",
    "explanation": "Price is -99.9, which fails Price >= 0. Rule impact: Field Price cannot be negative.",
    "rule_source": "rules_mifid.json#MIFID-2", "severity": null, "category": "negative_value", "conditional": false
  }],
  "total": 55, "distinct_trades": 53, "page": 1, "page_size": 25, "total_pages": 3
}
```

`GET /api/impact-matrix/{id}/export?status=FAIL` → `text/csv` with columns
`Trade_ID, Asset_Class, Regulator, Rule_ID, Rule_Description, Status, Affected_Field, Actual_Value, Expected_Condition, Explanation, Rule_Source, Severity, Failure_Category`.

`POST /api/rules/validate`

```json
{"regulator": "Demo", "rules": [{"id": "DEMO-1", "description": "Price positive", "logic": {">": [{"var": "Price"}, 0]}}]}
```

→ `{"valid": true, "rules": [{"id": "DEMO-1", "logic_text": "Price > 0", "errors": [], "warnings": [], …}], …}`

`POST /api/gap-analysis` `{"regulators": ["MiFID II"], "include_schema_validation": true}` → `rule_findings.by_category[]` (category, failed evaluations, impacted trades, trade ids, rule ids, fields, examples), `rule_findings.conditional_requirements`, and a separate `schema_findings.by_check[]` from `reporting_schema.json`.

`GET /api/checklist?trade_id=T000004` → per-rule `{rule_id, description, applicability, status, explanation, actual_values, rule_source}`; without `trade_id`, per-rule counts and `COMPLIANT | NON_COMPLIANT | NOT_APPLICABLE | ERROR`.

`POST /api/trades/query` `{"question": "Which trades are missing a Counterparty LEI?"}`

```json
{"matched": true, "interpretation": "Counterparty_LEI is missing", "count": 18, "trades": [{"Trade_ID": "T000003", "…": "…"}],
 "method": "deterministic pattern parser over the trade CSV (see SUPPORTED_PATTERNS)"}
```

Unsupported questions return `{"matched": false, "message": "Question not recognised. Supported patterns: …"}`.

## System

`GET /api/system/status` (abbreviated)

```json
{
  "overall": "ok",
  "services": [{"name": "search", "status": "ok", "latency_ms": 8.2,
                "checks": {"elasticsearch": {"ok": true, "detail": "cluster green"}, "database": {"ok": true, "detail": "ok"}}}],
  "elasticsearch": {"ok": true, "detail": "cluster green"},
  "postgresql": {"ok": true, "detail": "ok"},
  "rules": {"ok": true, "detail": "8 rule(s) in 3 file(s)"},
  "import": {"status": "completed", "files_processed": 10, "files_skipped": 0, "files_failed": 0, "…": "…"},
  "links": {"swagger_ui": "/api/docs", "openapi": "/api/openapi.json"}
}
```
