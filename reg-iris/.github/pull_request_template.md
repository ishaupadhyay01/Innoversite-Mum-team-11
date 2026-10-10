## What & why

## Module / team
- [ ] M1 Ingestion  - [ ] M2 Search  - [ ] M3 Rules  - [ ] Frontend/Integration  - [ ] Platform (libs, compose, CI)

## Contract changes
- [ ] No API / event / schema change
- [ ] API change — `docs/API.md` and frontend types updated
- [ ] Event payload change (`libs/iris-common/src/iris_common/events.py`) — consumers notified
- [ ] DB change — Alembic migration added and `alembic check` is clean

## Checks
- [ ] Tests added/updated (positive **and** negative case)
- [ ] `make lint test` passes locally
- [ ] No secrets, real client data or hard-coded URLs
