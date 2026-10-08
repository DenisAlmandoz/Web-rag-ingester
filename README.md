# Web Search Ingestion for RAG

A hands-on companion to `production-agentic-rag-course`: instead of ingesting arXiv
preprints, this project retrieves **arbitrary web content** via the [Tavily API](https://tavily.com)
and runs it through a transformation chain that makes it RAG-ready. Deployment is a
pair of [Databricks Declarative Automation](https://docs.databricks.com/en/dev-tools/bundles/index.html)
jobs.

```
                        ┌─────────────┐
   "any query" ───────▶ │   SEARCH    │  Tavily (or offline mock)
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   ranked URLs ───────▶ │   FETCH     │  httpx: redirects, timeouts, size cap, %PDF check
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   raw bytes ─────────▶ │   PARSE     │  baseline (bs4) · trafilatura · docling · unstructured
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   text ──────────────▶ │   CLEAN     │  unicode, wrappers, boilerplate lines, dedupe
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   clean text ────────▶ │   CHUNK     │  sentence-aware windows + overlap, title-prefixed → JSONL
                        └──────┬──────┘
                               ▼
                        documents.jsonl + chunks.jsonl  (ready to embed/index)
```

## The two jobs

The bundle (`databricks/`) stages one wheel (`src/web_ingestion`) and wires two jobs:

1. **`web-ingestion-pipeline`** — the ETL above. Runs `WebIngestion`:
   `extract` (Tavily search + fetch), `transform` (parse/clean/chunk), `load`
   (write `documents.jsonl` + `chunks.jsonl` into Delta tables via SQL warehouse).
   Widgets: `query`, `parser`, `max_results`, `catalog`, `schema`, `databricks_host`,
   `databricks_warehouse_id`, `tavily_api_key`.
2. **`web-ingest-vector-index`** — the indexing half. Runs `VectorIndex`:
   reads the chunks table produced by job 1 and syncs it to a managed
   [Databricks Vector Search](https://docs.databricks.com/en/vector-search/index.html)
   index with server-side embeddings. Widgets: `catalog`, `schema`, `chunks_table`,
   `documents_table`, `vs_endpoint_name`, `vs_index_name`, `embedding_model`,
   `databricks_host`, `databricks_warehouse_id`.

Entry points are two lines deep: `WebIngestion(WebIngestionConfig.from_widgets()).run()` /
`VectorIndex(VectorIndexConfig.from_widgets()).run()` (classes in `src/jobs/`, pushed to
Databricks via the wheel bundle: `web_ingestion` + `jobs` + `vector_index` packages).

## Deploy / run

Prereqs per target in [`databricks/databricks.yml`](databricks/databricks.yml):
a running SQL warehouse id, a secret scope `web-ingest` with key `tavily_api_key`,
and a serving endpoint `databricks-gte-large-en`.

```bash
uv sync --group dev               # local test/lint tooling
make install-parsers              # choose parsers for the job env (see below)
make install-databricks           # databricks-sdk for jobs/ + the lint/test extras

make bundle-validate TARGET=dev   # reads project_name/version from pyproject.toml
make bundle-deploy TARGET=dev
databricks bundle run web-ingestion-pipeline --target dev --refresh-all       # job 1
databricks bundle run web-ingest-vector-index --target dev --refresh-all      # job 2
```

Off-cluster, the job classes read the same settings from `.env` (see
`web_ingestion/config.py`); on Databricks they take overrides from the job widgets,
so the bundle variables are the source of truth in production.

Bundle variables `project_name` and `project_version` are sourced from
`pyproject.toml` (`[project].name` / `[project].version`): the Makefile targets
`make bundle-validate` / `make bundle-deploy` read them, and CI exports
`BUNDLE_VAR_PROJECT_VERSION` before `databricks bundle *` (DAB resolution order:
`--var` > `BUNDLE_VAR_*` env var > target/variable defaults). The version is propagated into
the two job descriptions so the deployed jobs self-report which package version
they run.

## Choosing parsers

Parsers live behind a lazy adapter interface (`web_ingestion/parsers/`), so the core
install runs fast and heavier parsers are opt-in:

| parser        | handles      | install                     |
|---------------|--------------|-----------------------------|
| `baseline`    | HTML         | built-in (beautifulsoup4)   |
| `trafilatura` | HTML         | `make install-trafilatura`  |
| `unstructured`| PDF + HTML   | `make install-unstructured` (spaCy model downloaded on first use) |
| `docling`     | PDF + HTML   | `make install-docling` — Linux/Docker or macOS 14+ |

A parser is selected per run via the pipeline job's `parser` widget. Install all
usable parsers on this machine with `make install-parsers`. Do **not** run
`uv sync --extra <one>` repeatedly to add parsers: uv replaces extras on each sync,
so pass them together (the Makefile targets handle this).

> **Why no docling here?** Docling pulls in `torch` and `docling-parse` (a C++
> extension). Current torch releases ship macOS 14+ arm64 wheels only, and
> `docling-parse` has to compile from source — which fails on this Mac's toolchain.
> It works fine in the course repo because that runs Docling inside a Linux Docker
> container. The `DoclingParser` adapter in this repo mirrors that container's
> `src/services/pdf_parser/docling.py`; on Linux/macOS 14+ just `make install-docling`.

## Going live with Tavily

1. Get a free key at https://app.tavily.com
2. Put it in `.env` locally, or in the `web-ingest` secret scope as `tavily_api_key` for the bundle targets.
3. When running the pipeline job, ensure the `tavily_api_key` widget is populated.

With a key set, search hits the real Tavily `/search` endpoint; without one, the
pipeline replays `fixtures/search_results.json` offline (see `--mock_mode` in
`web_ingestion/config.py`).

## Databricks Vector Index

The vector-index job hands the chunk table from job 1 to Databricks so retrieval can
happen against a managed vector index. The pattern mirrors the arxiv curator in
`oreilly-mlops-with-databricks`:

```
documents.jsonl ─┐
                 ├─SQL warehouse─▶ catalog.schema.web_documents (per-page metadata)
chunks.jsonl ────┘
                 └─SQL warehouse─▶ catalog.schema.web_chunks (Delta, CDF on)
                                        │  delta sync (TRIGGERED)
                                        ▼
                              catalog.schema.web_chunks_index
                              embeddings from databricks-gte-large-en (server-side)
```

`web_chunks` is the index source: `id` (primary key), `text` (embedding source),
plus `url`, `title`, `doc_id`, `chunk_index`, `char_count`, `approx_tokens`,
`ingest_ts`. `web_documents` keeps one row per page (`doc_id`, `url`, `title`,
`parser`, `raw_chars`, `cleaned_chars`, `chunk_count`, `metadata_json`) joined to
the chunks on `doc_id`.

Everything is guarded, so re-runs are safe: `CREATE SCHEMA/TABLE IF NOT EXISTS`,
Change Data Feed enabled via `ALTER TABLE`, `MERGE` on `id`/`doc_id`, `query()`
to re-read chunk rows, and exists-checks on the endpoint/index before
`create_delta_sync_index` + `sync()`.

> **Embeddings are generated by Databricks**, from the `text` column — nothing
> embeds locally, and the Delta Sync pipeline owns index freshness. The table is
> the contract: `id` (primary key), `text` (embedding source), plus `url`,
> `title`, `doc_id`, `chunk_index` for filtered retrieval.

The service principal needs `CAN CREATE TABLE` on the schema and permission to
manage the vector search endpoint.

## Output layout of one run

```
<output_dir>/runs/<timestamp>/
    search_results.json          what the provider returned
    raw/<slug>.html              untouched payloads (reproducibility)
    parsed/<parser>/<slug>.json  parser output before cleaning
    processed/documents.jsonl    cleaned text + metadata (one JSON object per doc)
    processed/chunks.jsonl       chunks ready to embed (id, text, url, title)
    report.md                    human-readable summary
```

`output_dir` defaults to `data` locally and to the system temp dir
(`$TMPDIR/web-ingestion`, typically `/local_disk0/tmp/web-ingestion` on cluster nodes)
inside the pipeline job, so job nodes never depend on a shared FS.

## Testing / lint

```bash
make setup      # uv sync --group dev
make test       # pytest (offline, no network)
make lint       # ruff check
make format     # ruff format
```

Tests in `tests/` exercise cleaning rules, chunk boundaries/overlap, mock search,
baseline extraction, the full pipeline in mock mode, the job classes, and the
Databricks table/vector-index statements — no API key or network needed. Local tests
must not use the real `.env` key: the `tavily_api_key` setting is overridden (empty
string) in the fixtures.