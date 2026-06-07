.DEFAULT_GOAL := help

# ── Local dev (no Docker) ─────────────────────────────────────────────────────

.PHONY: install
install: ## Install Python dependencies into .venv
	python3.11 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

.PHONY: migrate
migrate: ## Run all DB migrations (local postgres)
	psql -U postgres -d fintechdb -f migrations/000_schema.sql
	psql -U postgres -d fintechdb -f migrations/001_fraud_summary_mv.sql
	psql -U postgres -d fintechdb -f migrations/002_readonly_user.sql

.PHONY: run
run: ## Start the MCP server locally (HTTP, port 8000)
	.venv/bin/python3 src/server.py --sse

.PHONY: test
test: ## Run the manual test suite (blocked keywords + TTLCache)
	.venv/bin/python3 test_manual.py

# ── Docker (local, HTTP) ──────────────────────────────────────────────────────

.PHONY: build
build: ## Build the Docker image
	docker build -t fintech-fraud-mcp .

.PHONY: up
up: ## Start with Docker Compose (HTTP, port 8000)
	docker compose up

.PHONY: up-d
up-d: ## Start with Docker Compose in background
	docker compose up -d

.PHONY: down
down: ## Stop Docker Compose
	docker compose down

.PHONY: logs
logs: ## Tail logs from the running container
	docker compose logs -f app

# ── Docker dev (app + bundled postgres, auto-migrated + seeded) ──────────────

.PHONY: dev-up
dev-up: ## Start app + postgres with seed data (self-contained, no local DB needed)
	docker compose -f docker-compose.dev.yml up

.PHONY: dev-up-d
dev-up-d: ## Start dev stack in background
	docker compose -f docker-compose.dev.yml up -d

.PHONY: dev-down
dev-down: ## Stop dev stack
	docker compose -f docker-compose.dev.yml down

.PHONY: dev-logs
dev-logs: ## Tail dev stack logs
	docker compose -f docker-compose.dev.yml logs -f

.PHONY: dev-reset
dev-reset: ## Wipe the DB volume and restart fresh (re-runs all migrations + seed)
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.dev.yml up -d

# ── Docker (production, HTTPS) ────────────────────────────────────────────────

.PHONY: prod-up
prod-up: ## Start production stack (app + Caddy HTTPS) in background
	docker compose -f docker-compose.prod.yml up -d

.PHONY: prod-down
prod-down: ## Stop production stack
	docker compose -f docker-compose.prod.yml down

.PHONY: prod-logs
prod-logs: ## Tail production logs
	docker compose -f docker-compose.prod.yml logs -f

# ── Health & observability ────────────────────────────────────────────────────

.PHONY: health
health: ## Check server health
	curl -s http://localhost:8000/health | python3 -m json.tool

.PHONY: metrics
metrics: ## Show Prometheus metrics
	curl -s http://localhost:8000/metrics

# ── Claude Code integration ───────────────────────────────────────────────────

.PHONY: mcp-add
mcp-add: ## Register MCP server with Claude Code (local HTTP)
	claude mcp add --transport sse fintech-fraud http://localhost:8000/sse

.PHONY: mcp-add-prod
mcp-add-prod: ## Register MCP server with Claude Code (production HTTPS)
	@if [ -z "$(DOMAIN)" ]; then echo "Usage: make mcp-add-prod DOMAIN=fraud.yourdomain.com"; exit 1; fi
	claude mcp add --transport sse fintech-fraud https://$(DOMAIN)/sse

.PHONY: mcp-list
mcp-list: ## List registered MCP servers
	claude mcp list

# ── Cleanup ───────────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove .venv and Python cache files
	rm -rf .venv __pycache__ src/__pycache__
	find . -name "*.pyc" -delete

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
