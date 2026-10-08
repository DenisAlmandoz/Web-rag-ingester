.PHONY: help setup sync test lint format clean \
        install-trafilatura install-unstructured install-docling install-parsers \
        install-databricks bundle-validate bundle-deploy

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install core + dev dependencies
	uv sync --group dev

sync: ## Sync dependencies to lockfile state
	uv sync

install-trafilatura: ## Install the trafilatura HTML parser
	uv sync --extra trafilatura

install-unstructured: ## Install the Unstructured parser (spaCy model downloaded on first use)
	uv sync --extra unstructured

install-trafilatura-unstructured: ## Install both light parser extras (uv sync replaces extras, run together)
	uv sync --extra trafilatura --extra unstructured

install-docling: ## Install Docling (Linux/Docker or macOS 14+; heavy, downloads models)
	uv sync --extra docling

install-parsers: ## Everything except docling
	uv sync --extra trafilatura --extra unstructured

install-databricks: ## Databricks vector search SDK (keeps the other extras)
	uv sync --extra trafilatura --extra unstructured --extra databricks

PROJECT_VERSION := $(shell uv run python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null)

bundle-validate: ## Validate the DAB bundle (TARGET=dev|acc|prd, default dev)
	@export BUNDLE_VAR_PROJECT_VERSION="$(PROJECT_VERSION)" && \
		cd databricks && databricks bundle validate --target "$${TARGET:-dev}"

bundle-deploy: ## Deploy the DAB bundle (TARGET=dev|acc|prd, default dev)
	@export BUNDLE_VAR_PROJECT_VERSION="$(PROJECT_VERSION)" && \
		cd databricks && databricks bundle deploy --target "$${TARGET:-dev}"

test: ## Run tests
	uv run pytest -q

lint: ## Run ruff checks
	uv run ruff check src tests

format: ## Auto-format with ruff
	uv run ruff format src tests

clean: ## Remove test artifacts and caches
	rm -rf .pytest_cache .ruff_cache data/runs
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +