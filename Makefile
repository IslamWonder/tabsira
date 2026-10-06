# Every target delegates to a script in scripts/, so the same command works the
# same way from a terminal, from Jenkins and inside Docker. Names are fixed by
# AGENTS.md: add targets, never rename one.

.DEFAULT_GOAL := help

.PHONY: help install dev migrate data test coverage lint format eval smoke benchmark up security audit stats mock-photos mock-patch mock-data mock-texts mock-import mock-fill-in mock-clean

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{ printf "  make %-12s %s\n", $$1, $$2 }'

install: ## All dependencies: web, api, vision, git hooks
	@bash scripts/install.sh

dev: ## api + web (+ vision) with reload against tabsira.test
	@bash scripts/dev.sh

migrate: ## geodata chain, then app chain, then vectors chain
	@bash scripts/migrate.sh

data: ## Import corpora, ontology, learning path and vectors, once (DATA_FORCE=true to redo)
	@bash scripts/data.sh

test: ## Unit tests, web and api
	@bash scripts/test.sh

coverage: ## Tests with the 100 % threshold and HTML reports
	@bash scripts/test-coverage.sh
	@bash scripts/test-web-coverage.sh

lint: ## Format check, lint, type check (web and api)
	@bash scripts/lint.sh

format: ## Rewrite files the way the format check wants them
	@bash scripts/format.sh

eval: ## Gold scenes and the official contest cases
	@bash scripts/eval.sh

smoke: ## HTTP checks against a running app
	@bash scripts/smoke.sh

benchmark: ## Compare AI providers, detectors and rerankers on the same scenes
	@bash scripts/benchmark.sh

up: ## docker compose up, whole stack
	@bash scripts/up.sh

security: ## Blocking security gate: secrets and critical advisories
	@bash scripts/security-gate.sh

audit: ## Advisory audit: SAST, dependency advisories, hygiene
	@bash scripts/audit.sh

stats: ## A few lines about the code: size, tests, schema, docs, coverage, today
	@bash scripts/code-stats.sh

mock-data: ## Generate the mock members file (MOCK_SEED, MOCK_MEMBERS) into ../tabsira-data/mock
	@uv run --project tools/mockdata python -m mockdata.cli

mock-photos: ## Run the real pipeline over the placepix photos into ../tabsira-data/mock/photo-library.json (MOCK_ARGS)
	@PYTHONPATH="$(CURDIR)/apps/api" uv run --project tools/mockdata python -m mockdata.process photos $(MOCK_ARGS)

mock-patch: ## Put the photo library's insight of some photos into the mock file, nothing else: MOCK_PHOTOS=12,40
	@test -n "$(MOCK_PHOTOS)" || { echo "usage: make mock-patch MOCK_PHOTOS=<placepix ids, 12,40>"; exit 2; }
	@PYTHONPATH="$(CURDIR)/apps/api" uv run --project tools/mockdata python -m mockdata.process patch --photos "$(MOCK_PHOTOS)" $(MOCK_ARGS)

mock-texts: ## Write the mock posts' reflections and comments into the mock file (MOCK_ARGS)
	@PYTHONPATH="$(CURDIR)/apps/api" uv run --project tools/mockdata python -m mockdata.process texts $(MOCK_ARGS)

mock-import: ## Import the mock members of MOCK_FILE (a path or s3://bucket/key); MOCK_ARGS=--allow-production on production
	@test -n "$(MOCK_FILE)" || { echo "usage: make mock-import MOCK_FILE=<path or s3://bucket/key>"; exit 2; }
	@cd apps/api && uv run python -m src.cli.import_mock "$(MOCK_FILE)" --i-understand $(MOCK_ARGS)

mock-fill-in: ## Bring the mock rows already imported up to a later feature: MOCK_FILL_IN=views (names in tools/mockdata/README.md)
	@test -n "$(MOCK_FILL_IN)" || { echo "usage: make mock-fill-in MOCK_FILL_IN=<name>, e.g. views"; exit 2; }
	@cd apps/api && uv run python -m src.cli.import_mock $(foreach name,$(MOCK_FILL_IN),--fill-in $(name)) --i-understand $(MOCK_ARGS)

mock-clean: ## Delete every mock member (@mock.tabsira.me) and what they own; MOCK_ARGS=--allow-production on production
	@cd apps/api && uv run python -m src.cli.import_mock --clean --i-understand $(MOCK_ARGS)
