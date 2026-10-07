.PHONY: help setup sync test lint format run demo compare parsers \
        install-trafilatura install-unstructured install-docling install-parsers \
        install-databricks index clean

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

index: ## Push the latest chunks.jsonl to the Databricks vector index
	uv run web-ingest index

test: ## Run tests
	uv run pytest -q

lint: ## Run ruff checks
	uv run ruff check src tests

format: ## Auto-format with ruff
	uv run ruff format src tests

run: ## Full pipeline on default query (offline unless TAVILY_API_KEY set)
	uv run web-ingest run "attention is all you need transformer architecture explained"

demo: ## Offline end-to-end demo on bundled fixtures
	uv run web-ingest demo

search: ## Tavily search: make search 'your query'
	uv run web-ingest search

compare: ## Parse one fixture page with every installed parser
	uv run web-ingest compare attention-is-all-you-need --fixture pages/attention-is-all-you-need.html

parsers: ## Show which parsers are installed
	uv run web-ingest parsers

notebook: ## Launch jupyter lab
	uv run jupyter lab notebooks

clean: ## Remove test artifacts and caches
	rm -rf .pytest_cache .ruff_cache data/runs
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +