# Team-wise implementation plan

8 developers, 4 teams, working in parallel from day 1. The scaffold already runs end to end, so every team starts
from working code and a frozen contract instead of a blank page.

| Team | People | Owns | Path |
|---|---|---|---|
| **T1 Ingestion & Versioning** | 2 (T1-A, T1-B) | Module 1, `iris_ingestion` DB, parsers, What's New, alerts | `services/ingestion-service` |
| **T2 Search & Comparison** | 2 (T2-A, T2-B) | Module 2, ES mapping, Chroma, compare | `services/search-service` |
| **T3 Rules & Impact** | 3 (T3-A, T3-B, T3-C) | Module 3, rule engine, runs, matrix | `services/rules-engine-service` |
| **T4 Frontend & Integration** | 1 (T4) | SPA, gateway, compose, CI, seed/demo | `frontend/`, `gateway/`, `docker-compose.yml`, `.github/` |

`libs/iris-common`, `events.py` and `docs/` are **platform**: changes need one reviewer per team (CODEOWNERS).

## 0. How parallel work stays unblocked

1. **Contracts first, frozen at the end of Sprint 0**: `docs/API.md`, `frontend/src/api/types.ts`,
   `iris_common/events.py`, ES mapping, rule-file schema. Changes after that follow the additive-only rule.
2. **Every dependency has a fake** so no team waits for another:
   * T2 tests against `FakeIngestion` payloads and the `InMemoryBackend` (`SEARCH_BACKEND=memory`) — no ES needed.
   * T3 runs the engine purely in-process; search-service is optional for auto-linking.
   * T4 develops against the running scaffold (`docker compose up`), whose endpoints already return real data.
   * T1 tests with an in-process publisher that records the tasks it would send.
3. **Trunk-based Git**: short-lived `feature/<team>-<topic>` branches → PR to `main`; CI (lint, tests per service,
   migrations on Postgres, frontend build, image build) must be green; 1 reviewer from the owning team, +1 from each
   consumer team for contract changes. Conventional commits (`feat(rules): …`).
4. **Daily 10-minute integration sync** (one person per team) + a **Friday demo** on the compose stack seeded with
   `make seed`.

## 1. Sprint plan (4 one-week sprints; compress to days for a hackathon)

### Sprint 0 — Foundations (days 1–2, everyone)
| Who | Task | Done when |
|---|---|---|
| All | `make venv test`, `docker compose up --build`, `make seed`; read `ARCHITECTURE.md` | Everyone has the stack running locally |
| T4 | Protect `main`, enable CI, create team handles for CODEOWNERS | First PR goes through the full pipeline |
| Leads | Review & freeze contracts listed above | Signed off in a PR |

### Sprint 1 — Must-have core (Basic tasks in the brief)
| Team | Member | Work |
|---|---|---|
| T1 | A | Harden parsers on more real regulator formats (Article/Section/Annex headings, multi-column PDFs, tables); page-accurate clause spans; OCR decision for scanned PDFs |
| T1 | B | Versioning edge cases (concurrent activation test on Postgres, deactivate-last-version, re-process FAILED version endpoint); metadata-changed event for re-indexing |
| T2 | A | Real ES relevance tuning on the corpus (`queries.txt` as a golden set: target ≥ 8/10 top-3 hits); synonyms (LEI ↔ Legal Entity Identifier) |
| T2 | B | Index lifecycle: alias swap re-index command, `index-status` → readiness, reconcile job (versions in ingestion but missing in ES) |
| T3 | A | Engine: more operators if rules need them; property-based tests for operators; explanation wording review with a compliance SME |
| T3 | B | Runs: chunk pre-splitting for huge CSVs, cancel run, run retention/cleanup |
| T3 | C | Matrix API: pivot performance on 1M rows (EXPLAIN on Postgres), export of pivot view |
| T4 | — | Wire every page to real data, polish empty/error states, PDF opens at cited page |

### Sprint 2 — Intermediate tasks
| Team | Work |
|---|---|
| T1 | Alert Panel semantics (per-user read state when auth arrives), What's New detail page with diff, audit-log API filters |
| T2 | Facet counts that respect current filters; saved searches; compare UX for cross-regulation (align by semantic similarity, not only ref) |
| T3 | Rule-clause linking review flow (`PUT /rules/{id}/clause-link` UI with T4); severity-weighted stats; rule set diff between versions |
| T4 | Impact-matrix pivot heat-map, rule detail drawer, filter chips; Swagger links page; Playwright smoke test in CI |
| All | ≥ 8 unit tests per service (already met), plus one negative test per endpoint |

### Sprint 3 — Advanced (good-to-have)
| Team | Work |
|---|---|
| T2 | Semantic search on (`make up-semantic`), hybrid ranking (RRF), grounded Q&A endpoint `/api/v1/ask` that **only** answers from retrieved clauses and returns citations (Ollama + Phi-3/Mistral in a compose profile) |
| T3 | Rule authoring helper: suggest JSONLogic from a selected clause (LLM, human-approved), rule test-bench on sample trades |
| T1 | Near-duplicate detection at scale (ES `more_like_this` candidate generation) |
| T4 | Chat panel with citation chips; authentication at the gateway (OIDC) replacing the static token |

### Sprint 4 — Hardening & demo
Load test (100k-row CSV; 1k documents), failure drills (kill a worker mid-run → run completes), security review,
README/demo script rehearsal, final `docker compose up` ≤ 1 minute check.

## 2. What the scaffold already delivers vs. what each team builds next

| Requirement | Status in scaffold | Owner / next step |
|---|---|---|
| Upload new / updated documents | ✅ API + UI | T1 harden formats |
| Exact duplicates | ✅ SHA-256 unique + 409 | — |
| Similar documents & pre-upload suggestions | ✅ MinHash + filename + regulator + title | T1 scale via ES candidates |
| Version history, ACTIVE/INACTIVE, one ACTIVE | ✅ partial unique index + row lock, rollback | T1 concurrency test on PG |
| Compare versions + What's New + alerts | ✅ clause diff, cards, alert polling + toast | T1/T4 detail page |
| ES keyword search, filters, citations, clickable page refs | ✅ (verified with fake client + memory backend) | T2 relevance tuning on real ES |
| Compare two regulations / versions | ✅ `POST /compare`, UI | T2 semantic alignment |
| Semantic search | ⚙️ backend implemented, off by default (`ENABLE_SEMANTIC`) | T2 enable, evaluate, hybrid |
| Validate uploaded files (PDF/HTML/TXT, JSON, CSV) | ✅ | — |
| Configurable JSON rules, zero-code updates | ✅ upload, versioning, lint, dry-run | T3 authoring UX |
| PASS/FAIL + explanations + traceability | ✅ incl. NOT_APPLICABLE, lineage, auto-link (unconfirmed) | T3/T4 confirm-link flow |
| Impact Matrix, stats, filtering, pagination, CSV export | ✅ flat + pivot + stats + streaming export | T4 pivot UI |
| Batch processing for large CSVs | ✅ chunking + Celery chord fan-out (verified with real Redis) | T3 load test |
| Swagger, logging, errors, env config, Docker, CI | ✅ | T4 maintain |
| LLM Q&A with citations | ⏳ not started (optional) | T2 + T4, Sprint 3 |

## 3. Per-team definition of done
* Code + tests (positive **and** negative) in the owning service; `make lint test` green.
* API change reflected in `docs/API.md` and `frontend/src/api/types.ts` in the same PR.
* DB change = Alembic migration; `alembic check` clean; CI migration job green on Postgres.
* Logs are structured (no `print`); errors raise `IrisError` subclasses.
* Demoable on `docker compose up` + `make seed`.

## 4. Demo script (maps to the brief's Definition of Done)
1. `docker compose up --build` (≤ 1 min after first build) → `make seed`.
2. Dashboard shows **What's New** cards (regulator, effective date, short diff); bell shows alerts.
3. Upload `MiFID_II_2023_v2.pdf` again → **duplicate** blocked; upload a changed copy → match suggestion "new version of
   MiFID II" → new ACTIVE version, alert toast, diff.
4. Search "counterparty LEI requirement" → exact paragraph + clickable citation opening the PDF at the page; filter by
   regulator/jurisdiction/date; switch to semantic (if enabled).
5. Compare EMIR v1.0 ↔ v1.1 → added clauses highlighted (and the concatenated-document warning).
6. Impact analysis: rules JSON (show EMIR-1 lint warning) + trades CSV → run → stats, Impact Matrix filtered to FAIL,
   explanation "Price (-99.9) must be ≥ 0 — required by MiFID II rule MIFID-2 (…)", export CSV.
7. Swagger UIs on :8001/:8002/:8003; CI run with ≥ 8 tests passing (scaffold: 52 Python + 5 frontend).
