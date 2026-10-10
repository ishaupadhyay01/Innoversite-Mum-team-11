# ADR 0001 — Three microservices, database per service

**Status:** accepted

**Context.** Eight developers in four teams must work in parallel on three functional modules; the brief requires
independently deployable FastAPI services.

**Decision.** One service per module (ingestion, search, rules) plus a gateway and SPA. Each service owns its
database (`iris_ingestion`, `iris_search`, `iris_rules`), migrations, image and tests. Shared code is limited to
platform plumbing in `libs/iris-common`.

**Consequences.** Teams release independently and cannot break each other through schema changes. Cross-service data
is fetched over REST (`/internal/v1/...`) or carried in task payloads, which needs explicit contracts (see
`SERVICE_COMMUNICATION.md`). One Postgres instance hosts the three databases locally to keep startup under a minute.
