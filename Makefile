# PredomicsApp — common tasks. Run `make` to list them.
# Everything runs in Docker; nothing needs to be installed on the host except
# Docker (Compose >= 2.24).

COMPOSE      := docker compose
COMPOSE_DEV  := docker compose -f docker-compose.dev.yml
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.prod.yml
BASE_URL     ?= http://localhost:8001

.DEFAULT_GOAL := help
.PHONY: help up down logs build dev dev-down test test-backend test-frontend test-e2e test-e2e-url \
        lint check-config check-upgrade lock backup prod-up prod-down

help: ## List the available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Build and start the local stack (http://localhost:8001)
	$(COMPOSE) up -d --build

down: ## Stop the local stack (data volumes are kept)
	$(COMPOSE) down

logs: ## Follow the application logs
	$(COMPOSE) logs -f app

build: ## Build the production image only
	$(COMPOSE) build app

dev: ## Start the development stack with hot reload (frontend on :5173, API on :8000)
	$(COMPOSE_DEV) up -d --build

dev-down: ## Stop the development stack
	$(COMPOSE_DEV) down

test: test-backend test-frontend ## Backend and frontend unit tests

test-backend: ## Backend tests (pytest, real engine, SQLite in a temp dir)
	$(COMPOSE_DEV) run --rm --build backend-test

test-frontend: ## Frontend unit tests (vitest)
	$(COMPOSE_DEV) run --rm frontend-test

# The end-to-end tests register users and create projects: they get their own
# throwaway stack (project "predomics-e2e", no published ports, volumes removed
# afterwards) and never touch your running instance or its database.
E2E_IMAGE      ?= predomics-app:latest
E2E_STACK      := predomics-e2e
E2E_COMPOSE    := PREDOMICS_STACK=$(E2E_STACK) PREDOMICS_IMAGE=$(E2E_IMAGE) PREDOMICS_PORT=0 PREDOMICS_DB_PORT=0 \
                  docker compose -p $(E2E_STACK) -f docker-compose.yml
PLAYWRIGHT_IMG := mcr.microsoft.com/playwright:v1.58.2-noble
NGINX_IMG      := nginx:1.27-alpine

test-e2e: ## End-to-end tests (Playwright) on a throwaway stack built from E2E_IMAGE, through the NGINX proxy
	$(E2E_COMPOSE) up -d --no-build --wait
	docker run -d --rm --name $(E2E_STACK)-nginx --network $(E2E_STACK)_default \
		-e DOMAIN=_ -e NGINX_MAX_BODY=500M -e NGINX_TRUSTED_PROXY=127.0.0.1 \
		-v "$(CURDIR)/nginx/http:/etc/nginx/templates:ro" -v "$(CURDIR)/nginx/snippets:/etc/nginx/predomics:ro" \
		$(NGINX_IMG)
	docker run --rm --network $(E2E_STACK)_default \
		-v "$(CURDIR):/work" -v predomics-e2e-node-modules:/work/node_modules -v predomics-e2e-npm-cache:/root/.npm -w /work \
		-e BASE_URL=http://$(E2E_STACK)-nginx -e E2E_REQUIRE_CSP=1 -e CI=1 \
		$(PLAYWRIGHT_IMG) sh -c "npm ci --prefer-offline --no-audit --no-fund && npx playwright test"; \
	status=$$?; docker stop $(E2E_STACK)-nginx > /dev/null; $(E2E_COMPOSE) down -v; exit $$status

test-e2e-url: ## End-to-end tests against an existing instance: make test-e2e-url BASE_URL=http://host:port (needs Node.js; creates test users there)
	npm ci
	npx playwright install chromium
	BASE_URL=$(BASE_URL) npm run test:e2e

check-upgrade: ## Start the image on a v2.2.0 database and check that it migrates
	./scripts/check-upgrade.sh $(E2E_IMAGE)

lock: ## Recompute the --hash lines of backend/requirements.lock
	python3 scripts/hash-lock.py

lint: ## Lint the backend (ruff)
	$(COMPOSE_DEV) run --rm --build backend-test ruff check app tests

check-config: ## Validate the compose files and render the Helm chart
	$(COMPOSE) config -q
	$(COMPOSE_DEV) --profile test config -q
	DOMAIN=check.example.org POSTGRES_PASSWORD=x PREDOMICS_SECRET_KEY=0123456789abcdef0123456789abcdef \
		$(COMPOSE_PROD) config -q
	docker run --rm -v "$(CURDIR)/helm:/helm:ro" alpine/helm:3.16.2 lint /helm/predomicsapp

backup: ## Back up the database and the data volume into ./backups
	./scripts/backup.sh

prod-up: ## Build and start the production stack (needs .env, see DEPLOYMENT.md)
	$(COMPOSE_PROD) up -d --build

prod-down: ## Stop the production stack (data volumes are kept)
	$(COMPOSE_PROD) down
