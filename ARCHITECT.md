# ARCHITECT.md — Architecture of web-search-ingestion

## Problem statement recap
Turns web search results (Tavily) into clean, chunked text and syncs those chunks to a Databricks Vector Search index, ready for RAG.

## Current repo layout
- src/web_ingestion/ — core pipeline (no Databricks imports)
  - config.py — Settings, paths, databricks config, databricks_ready
  - search.py — search client (Tavily; fakes for offline)
  - fetch.py — HTTP fetch + optional cached HTML
  - parsers.py / models.py — parsers (baseline/html/trafilatura/unstructured/docling) + Result models
  - transform/clean.py, transform/chunk.py — cleaning + chunking
  - pipeline.py — orchestrate search→fetch→parse→clean→chunk
- src/jobs/ — Databricks job entry classes
  - web_ingestion.py — WebIngestionConfig + WebIngestion (extract→transform→load → Delta tables)
  - vector_index.py — VectorIndexConfig + VectorIndex (extract from Delta → transform → load → vector index)
  - widgets.py — notebook widget reader (bundle base_parameters)
- src/vector_index/ — Databricks runtime integration
  - table.py — ChunksTable, DocumentsTable (ensure, query, merge, SQL Statement Execution)
  - vector_index.py — VectorSearchManager (delta-sync index, server-side embeddings via databricks-gte-large-en, TRIGGERED)
  - client.py — env mirroring + WorkspaceClient factory
- tests/ — offline pytest (fakes), all passing
- databricks/ — Databricks Asset Bundle (DAB), repo root data/
  - databricks.yml — bundle name, whl artifact (uv build -> dist), include variables/resources, targets dev/acc/prd
  - variables.yml — catalog/schema/tables/endpoint/index/model/query/parser/max_results/schedule; project_name/project_version read from pyproject.toml (project_version overridable via BUNDLE_VAR_PROJECT_VERSION, exported by make bundle-* and CI)
  - resources/web_ingestion_pipeline.yml — job 1 (ingest → Delta tables), schedule 0 0 */6 * * ?, secrets/web-ingest/tavily_api_key
  - resources/vector_index.yml — job 2 (sync vector index), 0 30 */6 * * ?
  - notebooks/ — Databricks notebook entry points for the jobs
- .github/workflows/deploy.yml — CI/CD: lint/test/validate + deploy dev (push main), manual dispatch for acc/prd, optional run pipeline

## Data flow
1. Search (Tavily or fake) -> SearchResult list
2. Fetch URLs -> FetchedDocument (raw_html or text)
3. Parse (baseline/trafilatura/unstructured/docling) -> parsed title/text
4. Clean (whitespace, boilerplate) -> clean text
5. Chunk (recursive/simple, chunk_size/chunk_overlap) -> chunks
6. Persist: write chunks.jsonl/documents.jsonl to run_dir (local) or push to UC tables + Vector Search

## Databricks deployment (DAB)
- Bundle root: databricks/
- Wheel built by bundle artifact: `uv build --wheel --out-dir dist .`, `path: ../` (repo root;
  CLI runs the build with cwd = path and uploads `{path}/dist/*.whl`)
- Jobs use environments with dependencies ../dist/*.whl + databricks-vectorsearch==0.66
- Job 1 notebook: widgets/query/parser/max_results/catalog/schema/databricks_host/databricks_warehouse_id/tavily_api_key
- Job 2 notebook: widgets/catalog/schema/chunks_table/documents_table/vs_endpoint_name/vs_index_name/embedding_model/databricks_host/databricks_warehouse_id
- Notebooks are two-line entry points over the job classes:
  `WebIngestion(WebIngestionConfig.from_widgets()).run()` and
  `VectorIndex(VectorIndexConfig.from_widgets()).run()` (extract → transform → load)
- Vector index: delta-sync, pipeline_type=TRIGGERED, primary_key=id, embedding_source_column=text, embedding_model_endpoint_name=databricks-gte-large-en
- Auth: Databricks host/client_id/client_secret via env (SPN). Tavily via Databricks secret scope web-ingest/tavily_api_key.
- Targets: dev (personal root), acc/prd (Shared root). prd schedule UNPAUSED by default; dev/acc PAUSED.

## CI/CD
- GitHub Actions: .github/workflows/deploy.yml
  - quality: uv sync --group dev; ruff; pytest; databricks bundle validate (dev) if creds set
  - deploy: on push main -> dev only; on workflow_dispatch -> chosen target (dev/acc/prd); optional trigger web-ingestion-pipeline
  - concurrency per (event,target/ref)

## Env/Runtime
- Local: settings come from `.env` (see `web_ingestion/config.py`); `uv run pytest -q` exercises jobs/pipeline/parsers/databricks against fakes, no network.
- Databricks: jobs run notebooks that instantiate the job classes and call `run()`:
  job 1 stores the run's chunks/documents in UC Delta tables (`WebIngestion.load`),
  job 2 syncs the chunks into the delta-sync vector index (`VectorIndex.load`).
  Settings are injected as notebook widgets (`WebIngestionConfig.from_widgets()`), gated
  on `DATABRICKS_RUNTIME_VERSION` so module import never touches the SDK off-cluster.

## Key files
- src/web_ingestion/config.py, pipeline.py, src/jobs/*.py, src/vector_index/*.py
- databricks/databricks.yml, variables.yml, resources/*.yml, notebooks/*.py
- tests/test_index.py (vector_index fakes), tests/test_jobs.py (job classes), others offline
