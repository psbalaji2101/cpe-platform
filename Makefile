.DEFAULT_GOAL := help
SHELL := /bin/sh

DOCKER ?= docker
COMPOSE := $(DOCKER) compose
PYTHON ?= python3
VENV := .venv
VENV_PY := $(VENV)/bin/python
BENCHMARK_MIB ?= 64
BENCHMARK_LINE_BYTES ?= 512
TEST_IMAGE := cpe-evidence-browser-tests
# For Docker Engine on Linux: make test-e2e E2E_DOCKER_ARGS='--add-host=host.docker.internal:host-gateway'
E2E_DOCKER_ARGS ?=

.PHONY: help configure setup python-env samples build up deploy start stop down restart status logs health \
        test test-backend test-frontend test-e2e test-browser-image verify smoke test-restart benchmark format package clean

help: ## List available commands (default)
	@awk 'BEGIN {FS = ":.*## "; printf "\nCPE Evidence Workspace\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-21s %s\n", $$1, $$2} END {printf "\nVolumes are preserved by stop, down, restart and clean. No target deletes customer data.\n\n"}' $(MAKEFILE_LIST)

configure: ## Generate private local credentials; preserve existing configuration
	$(PYTHON) scripts/configure.py

python-env: $(VENV)/.ready ## Install pinned Python dependencies into a project-local virtualenv

$(VENV)/.ready: backend/requirements.txt
	$(PYTHON) -c 'import sys; sys.version_info >= (3,11) or sys.exit("Python 3.11+ required for local dependencies; use make PYTHON=python3.11")'
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install -r backend/requirements.txt
	@touch $(VENV)/.ready

samples: ## Generate labeled synthetic ZIP, TAR, TAR.GZ and configuration files
	$(PYTHON) scripts/sample_bundle.py

setup: configure python-env samples ## Prepare local credentials, Python environment, samples and frontend dependencies
	cd frontend && npm ci

build: configure ## Build application Docker images
	$(COMPOSE) build

up: configure ## Build and deploy the local stack; retain existing data
	$(COMPOSE) up -d --build
	$(COMPOSE) ps

deploy: up ## Alias for up

start: configure ## Start existing containers without rebuilding
	$(COMPOSE) start

stop: ## Stop application containers without removing data
	$(COMPOSE) stop

down: ## Remove project containers/network; preserve named data volumes
	$(COMPOSE) down

restart: ## Restart API, worker and web; preserve PostgreSQL and evidence
	$(COMPOSE) restart api worker web

status: ## Show running services and health status
	$(COMPOSE) ps

logs: ## Follow API and worker logs (Ctrl-C exits log viewing only)
	$(COMPOSE) logs --tail=100 -f api worker

health: ## Check the API from inside the running container
	$(COMPOSE) exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').read().decode())"

test-backend: build ## Run backend/security tests in an isolated ephemeral SQLite database
	$(COMPOSE) run --rm --no-deps \
	  --volume "$(CURDIR)/backend/tests:/app/tests:ro" \
	  --volume "$(CURDIR)/scripts:/scripts:ro" \
	  --env PYTHONPATH=/app api pytest -q -p no:cacheprovider

test-frontend: ## Compile/type-check the frontend using its Docker build stage
	$(DOCKER) build --target build -t cpe-evidence-frontend-check frontend

test-browser-image: ## Build the isolated Chromium/Playwright runner
	$(DOCKER) build -t $(TEST_IMAGE) -f frontend/Dockerfile.e2e frontend

test-e2e: configure samples test-browser-image ## Test the running deployment through Chromium (creates synthetic cases)
	$(DOCKER) run --rm --shm-size=1g $(E2E_DOCKER_ARGS) \
	  --mount "type=bind,source=$(CURDIR),target=/project" \
	  --mount type=volume,target=/project/frontend/node_modules \
	  $(TEST_IMAGE)

test: test-backend test-frontend ## Run backend/security checks and frontend compilation

verify: up test test-e2e health ## Build, deploy, test and check health end-to-end

smoke: python-env ## Exercise five concurrent clients against an existing synthetic case
	$(VENV_PY) scripts/deployment_smoke.py

test-restart: python-env ## Verify synthetic case/report persistence across an application restart
	$(VENV_PY) scripts/restart_smoke.py

benchmark: python-env ## Run synthetic upload/index benchmark (BENCHMARK_MIB=64, max 6144)
	$(VENV_PY) scripts/benchmark_ingestion.py --mib $(BENCHMARK_MIB) --line-bytes $(BENCHMARK_LINE_BYTES)

format: ## Format frontend source with the locked project formatter
	cd frontend && npm exec prettier -- --write src playwright.config.ts e2e

package: ## Create a portable source ZIP excluding credentials and runtime data
	$(PYTHON) scripts/package_source.py

clean: ## Remove only generated local build/test files; never secrets, samples or data volumes
	rm -rf frontend/dist frontend/test-results frontend/playwright-report backend/.pytest_cache
