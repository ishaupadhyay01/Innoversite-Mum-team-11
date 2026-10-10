# Reg IRIS — Intelligent Regulatory Repository & Impact Scanner

Reg IRIS is a microservices prototype for a bank's compliance team. It keeps a versioned repository of regulatory documents, finds the exact paragraph that answers a keyword search (with a citation to file, version and page), tells you what changed between document versions, and evaluates a trade dataset against JSON-defined reporting rules to produce an Impact Matrix.

It is built for the 2026 "Reg IRIS" use case (BNP Paribas, Mumbai) and runs entirely on the supplied, synthetic dataset.

> **Search is keyword search.** Elasticsearch BM25 with analyzers, phrase matching, filters and highlighting. There is no vector store, no embeddings, no LLM and no external API anywhere in the system.

---

## Contents

- [Features](#features)
- [Architecture at a glance](#architecture-at-a-glance)
- [Technology stack](#technology-stack)
- [Quick start](#quick-start)
- [Using the application](#using-the-application)
- [Dataset loading and findings](#dataset-loading-and-findings)
- [API](#api)
- [Running tests](#running-tests)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Further documentation](#further-documentation)

## Features

| Area | What it does |
| --- | --- |
| Ingestion | Upload PDF, HTML or TXT (drag and drop). Validates type, size and content; stores safely; extracts clauses page by page (PyMuPDF), by section (HTML, with anchors) or by paragraph (TXT, with line numbers). Jobs move through Queued → Processing → Indexed / Failed with the real failure reason. |
| Keyword search | BM25 over paragraph text, headings, titles and regulator; exact phrases in quotes; `-word` exclusion; query-time synonyms (LEI ↔ legal entity identifier, FX ↔ foreign exchange …); filters by regulator, jurisdiction, category, document type, effective date; latest / all / one-version scope; four sort orders; server-side pagination; highlighting rendered as text (no HTML injection); suggestions; "did you mean"; search history and analytics. |
| Citations | Every hit names regulator, file, version and page (PDF), section anchor (HTML) or line range (TXT). "View source" opens the original file at that page or section. Identical text appearing in other versions is flagged. |
| Versions & What's New | Version families from `parent_doc_id`; every upload of a new version keeps the old one, re-indexes, compares clauses with `difflib`, and creates a persisted alert (New Document / New Version / Added / Removed / Modified Clause — only those the diff supports). Side-by-side comparison with inline word diffs. |
| Alerts | Unread counter (polled), toast notification on new uploads, read/unread state, searchable history, links to the diff. |
| Rule engine | Generic, safe JSONLogic-style interpreter (no `eval`). Explicit PASS / FAIL / NOT_APPLICABLE / ERROR semantics, field-level explanations, transparent normalisation layer, zero-code rule updates with validate and reload endpoints. |
| Impact Matrix | Selected rules are combined with **AND**: a trade is compliant only if it passes every selected rule (one verdict per trade, with the rules it broke; 44 compliant / 156 non-compliant across all eight rules). Plus trades × rules with status, affected field, actual value, expected condition, explanation and rule source; filter, sort, paginate, row detail; CSV export protected against formula injection; summary CSV. |
| Gap analysis & checklist | Failures grouped by type (missing value, invalid format, disallowed value, negative value …), conditional requirements, separate reporting-schema findings; rule-by-rule checklist for the dataset or one trade. |
| Trade questions | Questions about trade data ("Which trades are missing a Counterparty LEI?") are answered by a deterministic parser over the CSV — not by keyword search. |
| Operations | Single `docker compose up --build`, health checks, migrations, idempotent seeding, structured JSON logs, audit trail, merged Swagger UI, GitHub Actions CI. |

## Architecture at a glance

```mermaid
flowchart LR
  UI[React UI<br/>nginx :3000] -->|/api| GW[Gateway :8000<br/>routing · merged OpenAPI · dashboard]
  GW --> ING[Ingestion :8001<br/>upload · parse · versions · diff · alerts]
  GW --> SRCH[Search :8002<br/>BM25 · filters · citations]
  GW --> RULES[Rules :8003<br/>JSON engine · Impact Matrix · gap · checklist]
  ING -->|/internal/index| SRCH
  RULES -->|related text lookup| SRCH
  SRCH --> ES[(Elasticsearch 8)]
  ING & SRCH & RULES --> PG[(PostgreSQL 16)]
  ING --- FS[(/data volume<br/>original files)]
```

Details, data model and flows: [ARCHITECTURE.md](ARCHITECTURE.md).

## Technology stack

- **Frontend:** React 18 + TypeScript, Vite 5, Tailwind CSS 3, TanStack Query 5, React Router 6, Recharts, lucide-react, sonner. Fonts (IBM Plex Sans / Serif / Mono) are bundled — nothing is fetched from the internet at runtime.
- **Backend:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, pandas, PyMuPDF, BeautifulSoup, jsonschema, `difflib`.
- **Storage:** Elasticsearch 8.15 (single node), PostgreSQL 16, Docker volumes for uploads.
- **Ops:** Docker Compose, GitHub Actions, pytest, ruff.

All dependency versions are pinned in `services/*/requirements.txt`, `shared/pyproject.toml` and `frontend/package.json`.

## Quick start

### Prerequisites

- Docker Desktop (Windows / macOS, including Apple Silicon) or Docker Engine + Compose v2 (Linux).
- **Memory:** allow Docker at least **4 GB** (Elasticsearch is capped at 1.5 GB with a 512 MB heap; the rest of the stack uses well under 1 GB).
- Free ports **3000** (UI) and **8000** (API). PostgreSQL (5433) and Elasticsearch (9200) are bound to `127.0.0.1` only.
- Internet access during the first `docker compose build` (to pull images and install packages). None is needed afterwards.

### Start

```bash
git clone <your-repo-url> reg-iris && cd reg-iris
docker compose up --build
```

No `.env` is required: every setting has a local-development default. Copy `.env.example` to `.env` to change ports, credentials or to require an API token.

Start-up order is enforced by health checks: PostgreSQL → migrations → Elasticsearch → search → ingestion & rules → gateway → UI. The ingestion service then imports the dataset in the background (about ten seconds for the supplied files).

To measure readiness on your machine and smoke-test the stack:

```bash
docker compose up --build -d && python scripts/verify_setup.py
```

The script reports how many seconds the stack needed to become ready and checks search, impact analysis, CSV export and Swagger. **The ≤ 1 minute target from the brief has not been measured** — see [Known limitations](#known-limitations).

### URLs

| What | URL |
| --- | --- |
| Application | http://localhost:3000 |
| Swagger UI (all services, merged) | http://localhost:8000/api/docs (also via http://localhost:3000/api/docs) |
| OpenAPI JSON | http://localhost:8000/api/openapi.json |
| System status (JSON) | http://localhost:8000/api/system/status |

### Stop / reset

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and delete database, index and uploads (clean re-import on next start)
```

## Using the application

**Keyword search** — *Regulatory search* page. Type `Counterparty LEI` and press Enter. Each result shows the paragraph (highlighted), and a citation margin with regulator, file, version tag and page. Use quotes for exact phrases (`"Mandatory Trade Reporting Fields"`), `-word` to exclude, the left rail to filter, and the scope switch for *Latest versions*, *All versions* or *One version*. Questions about trade data typed here (e.g. *Which trades are missing a Counterparty LEI?*) get a separate "trade data" answer from the rules service.

**Upload a document** — *Documents* → *Upload document*. Drop a PDF/HTML/TXT file. If the file name matches an existing document the form proposes "new version of …" with the next version label. Progress is shown live; when the job reaches *Indexed* an unread alert appears in the header bell and a toast pops up. A clearly labelled synthetic file for demos is provided: `demo/MiFID_II_2023_v3_DEMO.txt`.

**Compare versions** — *What's new* → *Compare versions*, or *Documents* → a document → *Compare with v1.0*. The page lists added (green), removed (red) and modified (indigo, with inline word changes) clauses side by side, each linked to its page.

**Run compliance analysis** — *Impact analysis* → choose dataset, regulations and rules (none selected = all; the selected rules are combined with AND) → *Run impact analysis*. The *Trade verdicts* panel shows one result per trade — compliant only if it satisfies every selected rule — with the rules each trade broke and a CSV export; click a Trade ID to see its rows in the matrix below. The Impact Matrix opens filtered to failures; click any row for the trade record, the rule (original and evaluated JSON, normalisation notes, applicability), the actual value, the expected condition and the explanation.

**Export** — on the Impact Matrix: *Export filtered CSV* (current filters), *Full CSV*, or *Summary CSV*. Exports are generated by the backend from stored results.

**Checklist and gaps** — *Compliance checklist*: rule-by-rule status for the dataset or for one Trade ID; switch to *Gap analysis* for failures grouped by type plus separate JSON-Schema findings.

**Rules** — *Rules* page lists each rule with its original JSON, evaluated logic and notes; *Validate a rule set* checks a pasted JSON document; *Reload rule files* picks up files added to `data/rules/` without restarting anything.

## Dataset loading and findings

On start-up the ingestion service runs an idempotent import of `data/` (the supplied ZIP, unchanged):

1. Reads `metadata/doc_metadata.csv`, normalises dates and labels, resolves version families through `parent_doc_id` chains.
2. For each file in upload-timestamp order: parses it, stores version and paragraph metadata in PostgreSQL, indexes paragraphs in Elasticsearch, marks the newest version of each family as latest, diffs it against its parent and records a What's New alert stamped with the **original** `upload_timestamp` (marked read, so historical documents are not presented as new today).
3. On restart, versions already indexed are skipped (verified against the index count), lost index content is re-indexed, and orphaned index entries are removed. Progress and errors are visible under *System health* and at `/api/imports/latest`.

The rules service loads `rules/*.json`, `schema/reporting_schema.json` and `trades/*.csv` directly.

### Data issues found and how they are handled

| Finding | Handling |
| --- | --- |
| Effective dates like `01-07-23` | Day/month order inferred from the column (`15-01-21`, `30-11-22` prove day-first); recorded as a note on each version. |
| `Dodd‑Frank` uses a non-breaking hyphen | Folded to `Dodd-Frank`; noted. |
| `EMIR_2021_v2.pdf` pages 2–3 contain a full copy of the Dodd-Frank text | Indexed exactly as the file reads, so citations stay true; identical-text flags show the duplication in search results; the EMIR v1 → v1.1 diff reports those paragraphs as added. |
| `EMIR_2021_v1.pdf` page 2 has no text | Reported as an extraction warning on the version. |
| Schema uses `$$schema` and `$$` anchors | Treated as `$schema` / `$`; noted. |
| EMIR-1 and MIFID-1 pass the bare field name to `regex` | Generic normaliser rewrites a string that exactly names a trade field to `{"var": field}`; noted per rule. |
| EMIR-1 logic would fail every non-derivative | Applicability declared as data in `config/rules_overlay.json` (with written rationale) → 165 non-derivatives are NOT_APPLICABLE. |
| MIFID-4 compares `toNumber("2024-06-25")` with `"20180101"` | Documented engine extension: `toNumber` converts ISO dates to `YYYYMMDD`. One trade (T000005, 2017-12-31) fails. |
| FCA-2 as written requires LEI **and** ISIN for every non-FX trade | Evaluated as written (132 failures, mostly equities/bonds/commodities with no ISIN). It is flagged here rather than silently reinterpreted. |
| Query 8 asks about "2022 vs 2023 EMIR" | The dataset contains EMIR 2021 v1.0 and v1.1 only; the comparison page offers those. |

Results on the supplied data (8 rules × 200 trades = 1,600 evaluations): **209 FAIL, 1,021 PASS, 370 NOT_APPLICABLE, 0 ERROR; 156 trades fail at least one rule.** These figures are asserted by the test suite.

## API

Every endpoint is documented in Swagger at `/api/docs`. Highlights (full list with examples in [docs/API.md](docs/API.md)):

```bash
# keyword search with a filter
curl -s localhost:8000/api/search -H 'Content-Type: application/json' \
  -d '{"query":"Counterparty LEI","filters":{"regulators":["MiFID II"]},"scope":"latest"}' | jq '.results[0].citation'

# run the impact analysis and download the failures as CSV
ID=$(curl -s -XPOST localhost:8000/api/impact-matrix -H 'Content-Type: application/json' -d '{}' | jq -r .id)
curl -s "localhost:8000/api/impact-matrix/$ID/export?status=FAIL" -o impact_failures.csv

# upload a new version of an existing document (document id from GET /api/documents; MiFID II is 1 after a fresh import)
curl -s -F file=@demo/MiFID_II_2023_v3_DEMO.txt -F document_id=1 -F version_label=v3.0 localhost:8000/api/documents/upload
```

Errors always use one envelope: `{"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}`.

## Running tests

```bash
# all suites (each service is tested in isolation)
pip install -r services/ingestion-service/requirements.txt -r services/search-service/requirements.txt \
            -r services/rules-service/requirements.txt -r services/gateway/requirements.txt pytest==8.3.4
pip install ./shared
./scripts/run_tests.sh

# optional integration tests
export ES_TEST_URL=http://localhost:9200                                   # real Elasticsearch
export TEST_POSTGRES_URL=postgresql+psycopg://user:pass@localhost:5432/db  # migration drift check (drops the public schema!)

# lint and frontend
ruff check services shared scripts && ruff format --check services shared scripts
cd frontend && npm install && npm run typecheck && npm run build
```

What the tests cover and what was actually executed during development: [docs/TESTING.md](docs/TESTING.md).

## Configuration

| Variable | Default (compose) | Purpose |
| --- | --- | --- |
| `POSTGRES_USER / _PASSWORD / _DB` | `regiris` / dev password / `regiris` | Database credentials (development values) |
| `INTERNAL_TOKEN` | dev value | Shared secret for service-to-service `/internal/*` routes; the gateway never exposes them |
| `API_TOKEN` | empty | If set, uploads, rule reloads, analysis runs and alert updates need `Authorization: Bearer …` (enter it in the UI under *System health*) |
| `FRONTEND_PORT`, `GATEWAY_PORT` | 3000, 8000 | Host ports |
| `MAX_UPLOAD_MB` | 25 | Upload limit |
| `ES_JAVA_OPTS` | `-Xms512m -Xmx512m` | Elasticsearch heap |
| `LOG_LEVEL` | INFO | JSON logs on stdout |

Editable configuration in `config/`: `synonyms.txt` (query-time synonyms; recreate the index after changes), `query_noise_words.txt` (question words dropped from free-text queries), `rules_overlay.json` (reviewed applicability declarations and field aliases).

## Troubleshooting

- **Elasticsearch exits or stays unhealthy** — give Docker at least 4 GB of memory. On Linux, if logs mention `vm.max_map_count`, run `sudo sysctl -w vm.max_map_count=262144`.
- **Port already in use** — set `FRONTEND_PORT` / `GATEWAY_PORT` in `.env`.
- **Search returns 503** — Elasticsearch is not ready yet; *System health* shows the status of each dependency.
- **Dashboard shows no documents** — the import may still be running; see *System health → Dataset import* for the log, or run `python scripts/seed_data.py`.
- **Start from scratch** — `docker compose down -v && docker compose up --build`.
- **Upload rejected** — the message names the reason (type, size, not a real PDF, identical to an existing version, duplicate version label).

## Known limitations

- **Verification status.** The development environment had no access to Docker Hub, PyPI or npm. The parsers, rule engine, analysis, diff, query builder, export and trade-query logic were run and tested there against the supplied data; the FastAPI layer, database code, live Elasticsearch behaviour, React build and Docker Compose start-up were written but first run in CI or on your machine. See [docs/TESTING.md](docs/TESTING.md) for the exact list. Expect to run `docker compose up --build` and the CI workflow once before a demo.
- **Start-up time** is not measured; use `scripts/verify_setup.py`. Elasticsearch alone usually needs 20–40 s on a laptop.
- No `package-lock.json` is committed (it could not be generated offline). Direct dependencies are pinned exactly; transitive ones are resolved at build time. Run `npm install` once and commit the lock file for fully reproducible frontend builds.
- PDF extraction needs a text layer; scanned PDFs are reported as having no extractable text (no OCR).
- "Modified clause" means textually similar (≥ 55 % similarity or the same heading); the comparison makes no claim about legal significance.
- The rule files contain no document citations. The UI shows the rule file as the authoritative source and, separately, keyword-search matches from the same regulator labelled as informational.
- Synonyms are inline index settings; changing them requires recreating the index.
- Optional advanced features from the brief that are intentionally **not** implemented: semantic/vector search and the LLM chat assistant (excluded by design).
- Shared PostgreSQL database with per-service table ownership, chosen to keep the local footprint small; a production deployment would split databases.

## Further documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — services, data model, indexing, ingestion, rule evaluation, versioning.
- [docs/API.md](docs/API.md) — endpoints with example requests and responses.
- [docs/RULES.md](docs/RULES.md) — rule file format, operators, applicability and normalisation.
- [docs/TESTING.md](docs/TESTING.md) — test inventory and verification record.
- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) — a 4-minute demonstration script.
