# HR Platform — Makefile
# https://github.com/Keyou430/HR

COMPOSE_DEV  := docker compose -f docker/compose.base.yml -f docker/compose.dev.yml
COMPOSE_PROD := docker compose -f docker/compose.yml

.PHONY: help dev down logs build prod test test-smoke lint format migrate migration shell psql clean clean-db frontend seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

dev: ## Start development environment (api + postgres)
	$(COMPOSE_DEV) up -d
	@echo "API:      http://localhost:8000/docs"
	@echo "Frontend: cd frontend && npm run dev"

down: ## Stop development environment
	$(COMPOSE_DEV) down

logs: ## Tail API logs
	$(COMPOSE_DEV) logs -f api

build: ## Build production image
	docker build -t hr-platform -f docker/Dockerfile .

prod: ## Start production stack (api + postgres + nginx + backup)
	$(COMPOSE_PROD) up -d

test: ## Run full test suite
	$(COMPOSE_DEV) exec api pytest -v

test-smoke: ## Run smoke tests only
	$(COMPOSE_DEV) exec api pytest -v -m smoke

lint: ## Run all linters (ruff + biome)
	cd backend && ruff check .
	cd frontend && npx biome check .

format: ## Auto-format all code
	cd backend && ruff format .
	cd frontend && npx biome check --write .

migrate: ## Run Alembic migrations
	$(COMPOSE_DEV) exec api alembic upgrade head

migration: ## Generate Alembic migration (set MSG="description")
	$(COMPOSE_DEV) exec api alembic revision --autogenerate -m "$(MSG)"

shell: ## Open bash shell in API container
	$(COMPOSE_DEV) exec api bash

psql: ## Open psql in Postgres container
	$(COMPOSE_DEV) exec postgres psql -U hr_user -d hr_platform

clean: ## Remove caches and stop containers
	$(COMPOSE_DEV) down
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist

clean-db: ## Reset database (delete volumes + re-seed)
	$(COMPOSE_DEV) down -v

frontend: ## Start frontend dev server (host machine)
	cd frontend && npm run dev

seed: ## Re-run dev seed script
	$(COMPOSE_DEV) exec api python /app/scripts/seed_dev.py
