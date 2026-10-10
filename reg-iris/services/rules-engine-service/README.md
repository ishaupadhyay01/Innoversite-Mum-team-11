# rules-engine-service — Module 3: Rules Validation & Trade Impact Analysis

Owner: **Team 3** (3 devs). Port `8003` (Swagger: http://localhost:8003/docs). Database: `iris_rules`. Queue: `rules`.

## Responsibilities
Rule-set upload (JSON schema validation, operator compilation, field checks, lint, versioning per regulator) ·
trade CSV validation against the reporting schema · batch evaluation (chunked, parallel chord) · explanations ·
Impact Matrix (flat + pivot), statistics, filters, pagination, streaming CSV export · single-trade evaluation ·
rule → clause traceability (declared, or auto-suggested via search-service).

## Layout
```
app/
  engine/        jsonlogic.py (evaluator) · operations.py (custom ops) · explain.py · evaluator.py (PASS/FAIL/N-A/ERROR)
                 linter.py · loader.py · rule_file.schema.json            ← pure, no I/O
  trades/        schema.py (reporting schema) · validation.py (CSV report) · reader.py (chunked, typed)
  services/      rulesets.py · datasets.py · runs.py (execution) · matrix.py (queries/stats/export) · traceability.py
  api/v1/        rulesets.py · datasets.py · runs.py · evaluate.py
  tasks.py       rules.execute_run · rules.evaluate_chunk · rules.finalize_run · rules.link_rule_clauses
```

## Tuning
`CHUNK_SIZE` (rows per transaction, default 5000) · `FANOUT_THRESHOLD_ROWS` (above → parallel chord, default 50k) ·
`INSERT_BATCH_SIZE` · scale workers with `RULES_WORKER_CONCURRENCY` or more `rules-worker` replicas.

## Suggested split for 3 developers
* **T3-A Engine** — `engine/` (operators, explanations, linter), property tests
* **T3-B Execution** — `trades/`, `services/runs.py`, `tasks.py`, performance
* **T3-C Matrix & traceability** — `services/matrix.py`, `services/traceability.py`, `api/v1/runs.py`

## Backlog
- [ ] Pre-split large CSVs into chunk files (avoid re-scanning with `skiprows`)
- [ ] Partition `validation_results` by `run_id`; retention policy for old runs
- [ ] Cancel run; re-run with a different rule-set selection
- [ ] Rule-set diff between versions; rule test-bench endpoint
- [ ] Severity-weighted compliance score
