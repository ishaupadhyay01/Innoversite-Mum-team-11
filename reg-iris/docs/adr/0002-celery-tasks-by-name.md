# ADR 0002 — Asynchronous integration via Celery tasks sent by name

**Status:** accepted

**Context.** Parsing, indexing and rule evaluation are slow and must not block HTTP requests. The mandated stack is
Redis + Celery. Services must not import each other's code.

**Decision.** Producers call `send_task("<owner>.<action>", kwargs)`; task names, queues and payloads are declared in
`iris_common.events`. Each service's worker consumes only its own queue. Events are sent after commit; consumers are
idempotent; `acks_late` gives at-least-once delivery.

**Consequences.** Simple, observable, retryable. Fan-out to several consumers of one fact would need either multiple
tasks or a log (Redis Streams/Kafka) later.
