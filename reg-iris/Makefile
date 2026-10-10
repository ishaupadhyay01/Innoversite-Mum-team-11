# Reg IRIS developer commands.  `make help` lists them.
SERVICES := ingestion-service search-service rules-engine-service
PY ?= python3.12

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env  ## Build and start the whole stack (UI on http://localhost:8080)
	docker compose up --build -d
	@echo "UI/Gateway: http://localhost:8080   Swagger: :8001/docs :8002/docs :8003/docs"

up-semantic: .env  ## Start the stack including ChromaDB semantic search
	ENABLE_SEMANTIC=true docker compose --profile semantic up --build -d

down:  ## Stop the stack
	docker compose down

clean:  ## Stop the stack and delete all volumes (data!)
	docker compose down -v

logs:  ## Follow logs of all services
	docker compose logs -f --tail=100

ps:  ## Show container status
	docker compose ps

seed:  ## Load the sample dataset (regulations, rules, trades) and run an analysis
	$(PY) scripts/seed_sample_data.py --base-url http://localhost:8080

venv:  ## Create .venv with all service dev dependencies (for running tests locally)
	$(PY) -m venv .venv
	.venv/bin/pip install -q -e libs/iris-common $(foreach s,$(SERVICES),-r services/$(s)/requirements-dev.txt)

test:  ## Run every Python test suite (needs `make venv`)
	cd libs/iris-common && ../../.venv/bin/pytest
	@for s in $(SERVICES); do echo "── $$s"; (cd services/$$s && ../../.venv/bin/pytest) || exit 1; done

test-%:  ## Run one service's tests, e.g. make test-rules-engine-service
	cd services/$* && ../../.venv/bin/pytest

lint:  ## Lint Python (ruff) and frontend (eslint + tsc)
	.venv/bin/ruff check libs services scripts
	cd frontend && npm run lint && npm run typecheck

fmt:  ## Auto-format Python
	.venv/bin/ruff format libs services scripts
	.venv/bin/ruff check --fix libs services scripts

migration-%:  ## New Alembic revision, e.g. make migration-ingestion-service m="add column"
	cd services/$* && ../../.venv/bin/alembic revision --autogenerate -m "$(m)"

frontend-dev:  ## Vite dev server on :5173 (proxies /api to the gateway on :8080)
	cd frontend && npm install && npm run dev
