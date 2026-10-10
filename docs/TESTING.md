# Testing

## How to run

```bash
./scripts/run_tests.sh          # runs shared/, then each service's tests/ in isolation
```

Each service is tested from its own directory because every service has a package named `app`. Optional environment variables enable integration tests:

| Variable | Enables |
| --- | --- |
| `ES_TEST_URL` (e.g. `http://localhost:9200`) | `services/search-service/tests/test_es_integration.py` against a real Elasticsearch node (creates and deletes a temporary index) |
| `TEST_POSTGRES_URL` | `shared/tests/test_migrations.py` — **drops and recreates the `public` schema**, applies the migration and compares it with the models |

GitHub Actions (`.github/workflows/ci.yml`) runs ruff (lint + format check), all suites with PostgreSQL and Elasticsearch service containers, the frontend type-check and production build, and `docker compose build`.

## Inventory (126 tests)

### Ingestion service — 42

| File | Tests | Covers |
| --- | ---: | --- |
| `test_parsers.py` | 14 | PDF extraction with real page numbers (MiFID v2), clause spanning pages 2–3 (EMIR v2), embedded title kept as its own clause, HTML sections/anchors/lists without invented pages, script removal, TXT paragraphs with line numbers, heading detection (6 cases), corrupt PDF, empty text |
| `test_metadata.py` | 6 | `01-07-23` style dates and day-first inference, conflicting conventions rejected, regulator label folding, parent chains incl. grandparents and unknown parents, family keys, missing columns |
| `test_diffing.py` | 5 | MiFID v1 → v2 = exactly one added clause on p. 2, reverse = removed, modified clause with inline diff, identical documents, word-level segments |
| `test_storage.py` | 9 | Path traversal in file names, real PDF accepted, five rejection cases (type, fake PDF, binary text, empty, HTML without markup), size limit, storage confined to the upload root |
| `test_api.py` | 8 | *(FastAPI + SQLAlchemy + SQLite; fake search client)* full dataset import (10 versions, historical read alerts, latest flags), **repeated import without duplication**, listing and versions, compare endpoint, source file served byte-for-byte, upload of a new version → indexed job → unread alert with `["New Version", "Added Clause"]` → mark read, upload validation (400 / 422 / 409), 404 error envelope |

### Search service — 30

| File | Tests | Covers |
| --- | ---: | --- |
| `test_query_builder.py` | 14 | Phrase / term / exclusion parsing, noise-word removal, cross-fields BM25 with heading boost and `minimum_should_match`, exact-phrase fields without synonyms, `must_not`, match modes, filter combination and scopes, pagination / sort / highlight / facets in the body, browse mode, invalid paging (4 cases) |
| `test_highlight_and_citations.py` | 5 | Highlight segments unescaped as text (HTML-injection safe), best-variant selection, PDF page citation and URL, HTML anchor citation without pages, TXT line citation |
| `test_mapping.py` | 2 | Synonym file loading; analyzers, char filter, query-time-only synonyms, keyword/date/integer fields, strict mapping |
| `test_search_service.py` | 3 | Against a fake ES client: citation + highlight + identical-text flags, relaxed retry when the strict query finds nothing (and correct `from_` client parameter), no-result handling with "did you mean" and hints |
| `test_es_integration.py` | 6 | *(real Elasticsearch)* "Counterparty LEI" ranks the LEI clause first from the latest version with a page citation, exact phrase, regulator filter and all-versions scope with identical-text flags, synonym expansion, negative-price query and empty results, suggestions and index stats |

### Rules service — 50

| File | Tests | Covers |
| --- | ---: | --- |
| `test_expressions.py` | 21 | 17 operator cases (`==`, `!=`, `>=` with coercion, between, `in` list/substring, `regex`, `substr`, `toNumber` incl. ISO dates, `and`/`or`/`not`/`if`/`missing`), missing operand is false, type mismatch raises, unknown operator / bad structure / static validation, truthiness |
| `test_rule_engine.py` | 9 | Supplied rules load valid with original JSON preserved and notes, **PASS**, **FAIL** with field-level explanations and categories, **NOT_APPLICABLE** for conditional rules and EMIR-1 on non-derivatives, invalid rule → **ERROR**, runtime type error → ERROR, zero-code rule addition, field alias + unknown-field warning, schema normalisation |
| `test_analysis.py` | 13 | CSV ingestion and schema-typed coercion, bad values reported, **Impact Matrix on the supplied data** (1,600 evaluations; 209 FAIL / 1,021 PASS / 370 N/A / 0 ERROR; 156 impacted trades; per-rule counts; deterministic), rule selection, gap analysis with separate schema findings, checklist (dataset and one trade), **CSV export** columns and formula-injection guard, five supported trade questions with expected counts, document questions not treated as trade questions |
| `test_api.py` | 7 | *(FastAPI + SQLAlchemy + SQLite)* rules listing, run + filter + sort, row detail with trade and honest citation, CSV export equals stored rows, **request validation** (invalid status, unknown dataset, no rules, page size), checklist / gap / trade query, validate endpoint |

### Gateway — 3

`test_gateway.py`: route ownership (internal paths never routed), token protection only on mutating endpoints, OpenAPI merge (public paths only, schema-name conflicts renamed, `x-service` tags).

### Shared — 1

`test_migrations.py`: *(PostgreSQL)* Alembic upgrade produces exactly the SQLAlchemy models (no autogenerate diff), then downgrade.

## Verification record (development environment)

The development sandbox had **no access to PyPI, npm or Docker Hub**, so FastAPI, SQLAlchemy, PyMuPDF, the Elasticsearch client, Vite and the Docker images could not be installed there. What was actually executed:

| Check | Result |
| --- | --- |
| Ingestion pure tests (parsers, metadata, diff, storage) | **34 passed** (PDF extraction ran on the `pypdf` fallback; CI runs it on PyMuPDF) |
| Search pure tests (query builder, highlight, citations, mapping, fake-ES service) | **24 passed** |
| Rules pure tests (expressions, engine, analysis, export, trade questions) | **43 passed** |
| Gateway pure tests | **3 passed** |
| `ruff check` and `ruff format --check` (ruff 0.16.8) | clean |
| `docker compose config` | valid |
| Frontend: esbuild syntax pass over every `.ts/.tsx`; `tsc --strict` with local type shims for third-party modules | no errors other than implicit-`any` on event handlers that the real React types resolve |
| FastAPI/SQLite API tests, Elasticsearch integration tests, migration drift test | **not run** (skipped: dependencies unavailable) |
| `docker compose up`, startup time, browser rendering | **not run** |

In short, 104 tests ran and passed; the 22 framework, database and Elasticsearch tests are written and wired into CI but had not run when this was written. Run `./scripts/run_tests.sh` with the integration variables, or push to GitHub, to complete verification.
