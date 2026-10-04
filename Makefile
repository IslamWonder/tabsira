# Every target delegates to a script in scripts/, so the same command works the
# same way from a terminal, from Jenkins and inside Docker. Names are fixed by
# AGENTS.md: add targets, never rename one.

.DEFAULT_GOAL := help

.PHONY: help install dev migrate data test coverage lint format eval smoke benchmark up security audit

help: ## List the targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{ printf "  make %-10s %s\n", $$1, $$2 }'

install: ## All dependencies: web, api, vision, git hooks
	@bash scripts/install.sh

dev: ## api + web (+ vision) with reload against tabsira.test
	@bash scripts/dev.sh

migrate: ## geodata chain, then app chain
	@bash scripts/migrate.sh

data: ## Import corpora, ontology and learning path; build indexes
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
