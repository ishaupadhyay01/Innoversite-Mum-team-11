# search-service — Module 2: Intelligent Search & Comparison

Owner: **Team 2** (2 devs). Port `8002` (Swagger: http://localhost:8002/docs). Database: `iris_search`. Queue: `search`.
Stores: Elasticsearch index `iris-clauses` (alias) · optional ChromaDB collection `iris-clauses`.

## Responsibilities
Index clauses on `search.index_document_version` · flip ACTIVE/INACTIVE on `search.version_status_changed` ·
keyword search with filters, highlights, pagination and clickable citations · facets · optional semantic search ·
clause-level comparison of any two versions or regulations · query analytics.

## Layout
```
app/
  backends/       base.py (protocols) · elastic.py · memory.py (tests/dev) · semantic.py (Chroma) · filters.py · es_mapping.json
  services/       indexer.py · search.py (citations) · compare.py
  api/v1/         search.py · compare.py
  tasks.py        search.index_document_version, search.version_status_changed
  deps.py         backend singletons (override in tests)
```

## Run locally without Elasticsearch
```bash
export DATABASE_URL=sqlite:///./dev.db SEARCH_BACKEND=memory INGESTION_URL=http://localhost:8001
../../.venv/bin/alembic upgrade head && ../../.venv/bin/uvicorn app.main:app --reload --port 8002
# index a version that exists in ingestion:
curl -X POST localhost:8002/api/v1/search/reindex/<version_id>
```
Semantic: `make up-semantic` (builds the image with `WITH_SEMANTIC=true`, starts ChromaDB, sets `ENABLE_SEMANTIC=true`).

## Backlog
- [ ] Relevance tuning against `data/sample_input/queries/queries.txt` (golden set, top-3 hit rate)
- [ ] Synonyms (LEI ↔ legal entity identifier, MiFID ↔ Markets in Financial Instruments Directive)
- [ ] Hybrid ranking (reciprocal rank fusion of keyword + semantic)
- [ ] Grounded Q&A endpoint (`/api/v1/ask`) with mandatory citations (Ollama, compose profile `llm`)
- [ ] Reconcile job: versions READY in ingestion but missing from the index
