# ADR 0003 — In-house JSONLogic evaluator

**Status:** accepted

**Context.** Rules must be data (JSONLogic). The sample rules use non-standard operators (`regex` with a field-name
argument, `toNumber`), and every failure needs a human-readable explanation. PyPI JSONLogic packages are unmaintained or
lack lazy custom operators.

**Decision.** A ~300-line evaluator (`rules-engine-service/app/engine/jsonlogic.py`) with a custom-operator registry,
strict-null comparisons, and a separate explanation layer that walks the failing branch.

**Consequences.** Full control over semantics and explanations; we own the tests (see `tests/test_jsonlogic.py`).
Deviation from JS semantics (`null >= 0` is false) is deliberate and documented.
