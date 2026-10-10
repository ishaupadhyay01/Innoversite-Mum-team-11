# iris-common

Shared, **dependency-light** library used by every Reg IRIS backend service.
It contains platform plumbing only — never business logic owned by one team.

| Module | Purpose |
|---|---|
| `config` | `BaseServiceSettings` — env-driven settings every service extends |
| `logging` | JSON structured logging + request-id context |
| `errors` | `IrisError` hierarchy + FastAPI handlers → uniform error envelope |
| `middleware` | `RequestContextMiddleware` (X-Request-ID, access log, timing) |
| `auth` | Optional static bearer-token guard |
| `pagination` | `PageParams`, `Page[T]` |
| `health` | `/health/live` + `/health/ready` router factory |
| `app_factory` | `create_app()` — one place that wires all of the above |
| `diff` | Clause-level document diff (used by Ingestion "What's New" and Search "Compare") |
| `events` | Celery task names, queues and event payload contracts between services |
| `http` | `ServiceClient` — httpx wrapper with retries and request-id propagation |
| `text` | Normalisation, hashing, shingling, Jaccard, regulator canonicalisation |

Changes here affect all teams: open a PR tagged `platform` and get one reviewer from each team (see `.github/CODEOWNERS`).
