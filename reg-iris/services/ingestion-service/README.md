# ingestion-service — Module 1: Ingestion & Version Management

Owner: **Team 1** (2 devs). Port `8001` (Swagger: http://localhost:8001/docs). Database: `iris_ingestion`. Queue: `ingestion`.

## Responsibilities
Upload (PDF/HTML/TXT) · content validation · SHA-256 exact-duplicate detection · pre-upload match suggestions ·
parsing into pages and citable clauses · ACTIVE/INACTIVE versions (one ACTIVE per document) · version diff ·
What's New cards · alerts · audit log · internal index payload for search-service.

## Layout
```
app/
  main.py            app factory wiring (Swagger, errors, health)
  config.py          env settings (DATABASE_URL, STORAGE_DIR, match thresholds…)
  models/            SQLAlchemy models (documents, versions, pages, clauses, diffs, cards, alerts, audit)
  schemas/           Pydantic API contracts
  parsers/           pdf.py (PyMuPDF) · html.py (BeautifulSoup) · txt.py · segmentation.py (clause headings) · registry.py
  services/          documents.py (upload/dedupe/match) · versioning.py · diffing.py (What's New) · processing.py (pipeline) · audit.py
  api/v1/            documents.py · versions.py · alerts.py · internal.py
  tasks.py           ingestion.process_version
  storage.py         FileStorage protocol + content-addressed local implementation
  publisher.py       outbound Celery tasks (search.index_document_version, search.version_status_changed)
migrations/          Alembic
tests/               parsers, API flows (SQLite + inline publisher)
```

## Run locally without Docker
```bash
make venv                                   # from repo root
cd services/ingestion-service
export DATABASE_URL=sqlite:///./dev.db STORAGE_DIR=./.data
../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --reload --port 8001
../../.venv/bin/pytest
```

## Backlog
- [ ] More heading styles (Annex, Recital, Schedule, numbered `1.2.3`) and table extraction
- [ ] `POST /versions/{id}/reprocess` for FAILED versions
- [ ] Emit metadata-changed event so search re-indexes filter fields after `PATCH /documents/{id}`
- [ ] Concurrency test for activation on Postgres (CI integration job)
- [ ] Candidate generation for match suggestions via ES `more_like_this` beyond ~5k documents
